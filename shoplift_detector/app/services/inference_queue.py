"""Plan-priority GPU inference queue (T1-09, DOC-05 §5.1).

Noisy-neighbor protection for the shared GPU pool. Every enqueued
inference job carries a priority derived from the tenant's plan tier:

    enterprise = 0  (highest — dedicated in Phase 3)
    pro        = 1
    starter    = 2
    trial      = 3

Ordering uses `(priority, sequence)` so ties break FIFO — a burst of
Pro customers sharing a bucket get serviced in arrival order.

Implementation intentionally small. The real pool lives inside the
inference worker (`ai_service.py`); this module gives that worker a
pluggable queue it can pull from while keeping the priority math
unit-testable with no GPU present.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from dataclasses import dataclass, field
from typing import Any

# Plan → priority. Lower number = serviced sooner. Not using an Enum
# because FastAPI handlers + workers sometimes have a raw plan string
# from the tenant row.
PLAN_PRIORITY: dict[str, int] = {
    "enterprise": 0,
    "pro": 1,
    "starter": 2,
    "trial": 3,
}

# When the plan column is NULL or an unknown string we treat the
# caller as if they were on trial — avoids accidentally granting
# enterprise speed to a misconfigured tenant.
UNKNOWN_PLAN_PRIORITY = PLAN_PRIORITY["trial"]


def priority_for_plan(plan: str | None) -> int:
    if plan is None:
        return UNKNOWN_PLAN_PRIORITY
    return PLAN_PRIORITY.get(plan, UNKNOWN_PLAN_PRIORITY)


@dataclass(order=True)
class _PQEntry:
    """`heapq` compares tuples element-by-element, so we use a dataclass
    with only the sort key fields comparable. `payload` is excluded
    from comparison because Job objects aren't naturally ordered."""

    priority: int
    sequence: int
    payload: Any = field(compare=False)


@dataclass
class InferenceJob:
    tenant_id: str
    camera_id: int
    plan: str
    submitted_at_monotonic: float

    @property
    def priority(self) -> int:
        return priority_for_plan(self.plan)


class PriorityInferenceQueue:
    """Async priority queue — enterprise jumps the line, ties stay FIFO.

    Backed by `heapq` with an asyncio `Event` for blocking `get()`.
    Not thread-safe on its own; the inference worker runs in a single
    asyncio task pool, which is sufficient for the single-GPU pilot.
    """

    def __init__(self) -> None:
        self._heap: list[_PQEntry] = []
        self._seq = itertools.count()
        self._not_empty = asyncio.Event()

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return not self._heap

    def put_nowait(self, job: InferenceJob) -> None:
        entry = _PQEntry(
            priority=job.priority,
            sequence=next(self._seq),
            payload=job,
        )
        heapq.heappush(self._heap, entry)
        self._not_empty.set()

    async def get(self) -> InferenceJob:
        while not self._heap:
            self._not_empty.clear()
            await self._not_empty.wait()
        entry = heapq.heappop(self._heap)
        if not self._heap:
            self._not_empty.clear()
        return entry.payload

    def pop_nowait(self) -> InferenceJob | None:
        """Non-blocking take — returns None when empty. Used by tests
        and by the worker's backpressure check."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap).payload

    def peek_priority(self) -> int | None:
        """Priority of the next job without removing it."""
        if not self._heap:
            return None
        return self._heap[0].priority
