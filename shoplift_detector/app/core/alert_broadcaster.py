"""In-process pub-sub broadcaster for Server-Sent Events (SSE).

Every SSE connection calls `subscribe()` to get its own asyncio.Queue.
When an alert is created, `publish()` fans the minimal payload out to
all connected queues. Each SSE handler then decides whether to forward
the event based on the connected user's org/store membership.

This is intentionally simple: a single process, in-memory bus. If the
deployment ever moves to multiple workers, replace with Redis Pub/Sub or
PostgreSQL LISTEN/NOTIFY without touching the SSE handler API.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class AlertBroadcaster:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """Return a new queue that will receive every published payload."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._queues.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove the queue when the SSE connection closes."""
        async with self._lock:
            self._queues.discard(q)

    async def publish(self, payload: dict) -> None:
        """Fan *payload* out to every connected SSE client.

        Drops the message for clients whose queue is full (slow consumer)
        rather than blocking the AI inference loop.
        """
        async with self._lock:
            targets = set(self._queues)
        dropped = 0
        for q in targets:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dropped += 1
        if dropped:
            logger.debug(
                "SSE broadcaster: dropped %d message(s) for slow consumer(s)", dropped
            )


# Module-level singleton — imported by ai_service and the SSE endpoint.
alert_broadcaster = AlertBroadcaster()
