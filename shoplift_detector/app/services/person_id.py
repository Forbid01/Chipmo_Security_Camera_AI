"""Person ID generator — `P-{store_id}-{YYYYMMDD}-{seq:04d}`.

Design constraints (Railway single-process deployment):
- In-memory counter per (store_id, date) — safe for single-process.
- On first use per (store_id, date) after a restart, the counter is
  initialised from the DB so sequence numbers never collide with IDs
  already issued on the same day.
- Counter increments are serialised with asyncio.Lock to avoid races
  within the same process (multiple async tasks dispatching alerts
  concurrently).
- No Redis dependency required.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)


class PersonIDGenerator:
    """Singleton generator — import `person_id_generator` at module level."""

    def __init__(self) -> None:
        # (store_id, "YYYYMMDD") → current sequence value
        self._counters: dict[tuple[int, str], int] = {}
        # Tracks which (store_id, date) pairs have been DB-initialised
        self._initialised: set[tuple[int, str]] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _db_count(self, db, store_id: int, date_str: str) -> int:
        """Count today's P-{store_id}-{date_str}-* alerts to seed counter."""
        try:
            result = await db.execute(
                text(
                    "SELECT COUNT(*) FROM alerts "
                    "WHERE store_id = :s "
                    "  AND person_id LIKE :prefix"
                ),
                {"s": store_id, "prefix": f"P-{store_id}-{date_str}-%"},
            )
            return int(result.scalar() or 0)
        except Exception as exc:
            logger.warning("person_id_db_count_failed store=%s: %s", store_id, exc)
            return 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(self, db, store_id: int) -> str:
        """Return the next `P-{store_id}-{YYYYMMDD}-{seq:04d}` ID.

        Thread/task-safe. Initialises from DB on first call per
        (store_id, date) so restarts don't re-issue today's IDs.
        """
        today = datetime.now(UTC).strftime("%Y%m%d")
        key = (store_id, today)

        async with self._lock:
            if key not in self._initialised:
                count = await self._db_count(db, store_id, today)
                self._counters[key] = count
                self._initialised.add(key)
                logger.debug(
                    "person_id_counter_init store=%s date=%s seed=%d",
                    store_id, today, count,
                )

            self._counters[key] += 1
            seq = self._counters[key]

        pid = f"P-{store_id}-{today}-{seq:04d}"
        logger.debug("person_id_generated %s", pid)
        return pid


# Module-level singleton — import this in callers.
person_id_generator = PersonIDGenerator()
