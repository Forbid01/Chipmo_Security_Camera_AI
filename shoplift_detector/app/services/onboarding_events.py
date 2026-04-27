"""Per-tenant in-memory pub/sub for onboarding progress (T4-12).

Publishers call `broker.publish(tenant_id, event)` from whichever
request handler moved the onboarding funnel forward (agent register,
camera discovery, camera test). Subscribers — WebSocket clients on
`/api/v1/onboarding/status` — receive events scoped to their own
tenant only.

Kept deliberately in-process for the MVP: the backend runs as a
single uvicorn worker, so a Python-level broker is sufficient.
Scaling to multiple workers requires swapping the implementation for
a Redis pub/sub transport — the public interface is pinned to a
`Broker` Protocol so that migration doesn't ripple through callers.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy — keep the set narrow so UI code is easy to switch on.
# ---------------------------------------------------------------------------

AGENT_REGISTERED = "agent_registered"
AGENT_HEARTBEAT = "agent_heartbeat"
CAMERA_DISCOVERED = "camera_discovered"
CAMERA_TESTED = "camera_tested"
INSTALLER_DOWNLOADED = "installer_downloaded"

EVENT_TYPES: frozenset[str] = frozenset({
    AGENT_REGISTERED,
    AGENT_HEARTBEAT,
    CAMERA_DISCOVERED,
    CAMERA_TESTED,
    INSTALLER_DOWNLOADED,
})


def make_event(
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Standard envelope. Callers pass the typed payload dict; we
    wrap it with `type` + `ts` so the UI reducer doesn't have to
    invent its own."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type}")
    return {
        "type": event_type,
        "ts": (now or datetime.now(UTC)).isoformat(),
        "payload": dict(payload or {}),
    }


# ---------------------------------------------------------------------------
# Broker protocol + in-memory implementation
# ---------------------------------------------------------------------------

class Broker(Protocol):
    async def publish(self, tenant_id: str, event: dict[str, Any]) -> None: ...
    async def subscribe(self, tenant_id: str) -> "Subscription": ...


class Subscription(Protocol):
    async def get(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...


class _Queue:
    """Thin asyncio.Queue wrapper with a bounded backlog so a slow
    websocket client cannot inflate memory by staying connected but
    never reading."""

    MAX_BACKLOG = 256

    def __init__(self):
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=self.MAX_BACKLOG
        )
        self._closed = False

    async def push(self, event: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event and retry — preserving liveness
            # over completeness is the right choice for progress UIs.
            try:
                _ = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def get(self) -> dict[str, Any]:
        return await self._queue.get()

    async def close(self) -> None:
        self._closed = True


class InMemoryBroker:
    """Dispatch events to every live subscription for a tenant."""

    def __init__(self) -> None:
        self._subs: dict[str, set[_Queue]] = defaultdict(set)
        # Retain the N most recent events per tenant so a subscriber
        # that joins during setup sees recent history rather than a
        # silent empty socket.
        self._replay: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=32)
        )
        self._lock = asyncio.Lock()

    async def publish(self, tenant_id: str, event: dict[str, Any]) -> None:
        tenant_id = str(tenant_id)
        async with self._lock:
            self._replay[tenant_id].append(event)
            queues = list(self._subs[tenant_id])
        for q in queues:
            await q.push(event)

    async def subscribe(self, tenant_id: str) -> _Queue:
        tenant_id = str(tenant_id)
        queue = _Queue()
        async with self._lock:
            self._subs[tenant_id].add(queue)
            history = list(self._replay[tenant_id])
        for past in history:
            await queue.push(past)
        return queue

    async def unsubscribe(self, tenant_id: str, queue: _Queue) -> None:
        tenant_id = str(tenant_id)
        async with self._lock:
            self._subs[tenant_id].discard(queue)
        await queue.close()

    def subscriber_count(self, tenant_id: str) -> int:
        return len(self._subs.get(str(tenant_id), set()))


# Module-level singleton — handlers import this directly. Tests inject
# their own instance via dependency overrides rather than monkey-
# patching this reference.
broker = InMemoryBroker()


__all__ = [
    "AGENT_HEARTBEAT",
    "AGENT_REGISTERED",
    "CAMERA_DISCOVERED",
    "CAMERA_TESTED",
    "EVENT_TYPES",
    "INSTALLER_DOWNLOADED",
    "InMemoryBroker",
    "broker",
    "make_event",
]
