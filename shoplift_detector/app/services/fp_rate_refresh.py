"""Hourly refresh of the `store_fp_rate_daily` materialized view.

Per the T02-07 spike decision we run a vanilla Postgres materialized
view instead of a TimescaleDB continuous aggregate. That means the
refresh cadence has to come from us.

Design:
- A single async `run_refresh_loop()` coroutine that sleeps between
  ticks (default 1 hour) and issues `REFRESH MATERIALIZED VIEW
  CONCURRENTLY` against the app's DB session.
- `CONCURRENTLY` keeps dashboards readable during refresh. Requires
  the unique index the T02-16 migration installs.
- Failures are logged but don't kill the loop — a transient DB blip
  shouldn't stop the next hour's refresh from running.
- Disable-able via `STORE_FP_RATE_REFRESH_ENABLED=0` so dev / tests can
  opt out of the background task.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.db.session import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 1 hour default matches docs/06-DATABASE-SCHEMA.md §4's
# `add_continuous_aggregate_policy(..., schedule_interval => INTERVAL '1 hour')`.
DEFAULT_REFRESH_INTERVAL_SECONDS: float = 3600.0


def _refresh_enabled() -> bool:
    raw = os.environ.get("STORE_FP_RATE_REFRESH_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def _refresh_interval_seconds() -> float:
    raw = os.environ.get("STORE_FP_RATE_REFRESH_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_REFRESH_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Invalid STORE_FP_RATE_REFRESH_INTERVAL_SECONDS=%r; "
            "falling back to default %s",
            raw,
            DEFAULT_REFRESH_INTERVAL_SECONDS,
        )
        return DEFAULT_REFRESH_INTERVAL_SECONDS
    # Guard against mis-configuration that would hammer the DB.
    return max(60.0, value)


async def _view_exists(db) -> bool:
    result = await db.execute(text("""
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'public'
          AND matviewname = 'store_fp_rate_daily'
        LIMIT 1
    """))
    return result.fetchone() is not None


async def refresh_once(*, concurrently: bool = True) -> bool:
    """Run one refresh pass. Returns True on success, False otherwise.

    `concurrently=False` is only for the very first refresh right after
    the migration, before any data has seeded the view.
    """
    async with AsyncSessionLocal() as db:
        try:
            if not await _view_exists(db):
                logger.debug(
                    "store_fp_rate_daily materialized view not present; "
                    "skipping refresh"
                )
                return False

            mode = "CONCURRENTLY " if concurrently else ""
            await db.execute(
                text(f"REFRESH MATERIALIZED VIEW {mode}store_fp_rate_daily")
            )
            await db.commit()
            return True
        except Exception as exc:
            # CONCURRENTLY refuses on an unpopulated view. Fall back to
            # a blocking refresh once so the loop self-heals on first
            # run after the migration.
            if concurrently and "CONCURRENTLY" in str(exc).upper():
                logger.info(
                    "CONCURRENTLY refresh failed on empty view; "
                    "falling back to blocking refresh"
                )
                try:
                    await db.rollback()
                    await db.execute(
                        text("REFRESH MATERIALIZED VIEW store_fp_rate_daily")
                    )
                    await db.commit()
                    return True
                except Exception as inner:
                    logger.error(
                        "Fallback REFRESH MATERIALIZED VIEW failed: %s", inner
                    )
                    await db.rollback()
                    return False

            logger.error("REFRESH MATERIALIZED VIEW failed: %s", exc)
            await db.rollback()
            return False


async def run_refresh_loop() -> None:
    """Long-running background task. Exits only on cancellation."""
    if not _refresh_enabled():
        logger.info(
            "store_fp_rate_daily refresh loop disabled by env flag"
        )
        return

    interval = _refresh_interval_seconds()
    logger.info(
        "store_fp_rate_daily refresh loop started (interval=%ss)", interval
    )

    # First iteration uses a non-concurrent refresh to handle the empty
    # post-migration view case; subsequent iterations go concurrent.
    first = True
    while True:
        try:
            await refresh_once(concurrently=not first)
        except asyncio.CancelledError:
            logger.info("store_fp_rate_daily refresh loop cancelled")
            raise
        except Exception as exc:
            logger.exception("Unexpected refresh error: %s", exc)
        first = False

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
