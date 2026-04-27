"""Per-channel delivery log repository (T5-09).

Called by the escalation dispatcher (`services/escalation_dispatcher.py`)
after every send attempt. Customer portal's
`GET /api/v1/alerts/{alert_id}/escalations` reads directly from here.

Pre-migration behaviour: every write is a no-op, every read returns
an empty list. Lets the alert fan-out path call this repo
unconditionally — deployments that haven't applied the migration yet
just don't get the audit trail.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


Channel = Literal["telegram", "email", "fcm", "sms"]
ALLOWED_CHANNELS: frozenset[str] = frozenset({"telegram", "email", "fcm", "sms"})


class AlertEscalationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._table_exists: bool | None = None

    async def _exists(self) -> bool:
        if self._table_exists is not None:
            return self._table_exists
        query = text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'alert_escalations'
            )
            """
        )
        try:
            result = await self.db.execute(query)
            self._table_exists = bool(result.scalar())
        except ProgrammingError:
            self._table_exists = False
        return self._table_exists

    async def log_delivery(
        self,
        *,
        alert_id: int,
        channel: Channel,
        recipient: str | None = None,
        delivered_at: datetime | None = None,
    ) -> int | None:
        """Record a successful delivery. Returns the row id, or None
        on the pre-migration schema (no-op)."""
        if channel not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(ALLOWED_CHANNELS)}: {channel!r}")
        if not await self._exists():
            return None
        query = text(
            """
            INSERT INTO alert_escalations (alert_id, channel, recipient, delivered_at)
            VALUES (:alert_id, :channel, :recipient, :delivered_at)
            RETURNING id
            """
        )
        result = await self.db.execute(
            query,
            {
                "alert_id": alert_id,
                "channel": channel,
                "recipient": recipient,
                "delivered_at": delivered_at or datetime.now(UTC),
            },
        )
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def log_failure(
        self,
        *,
        alert_id: int,
        channel: Channel,
        recipient: str | None = None,
        error: str,
    ) -> int | None:
        if channel not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(ALLOWED_CHANNELS)}: {channel!r}")
        if not await self._exists():
            return None
        query = text(
            """
            INSERT INTO alert_escalations (alert_id, channel, recipient, failed_at, error)
            VALUES (:alert_id, :channel, :recipient, :failed_at, :error)
            RETURNING id
            """
        )
        result = await self.db.execute(
            query,
            {
                "alert_id": alert_id,
                "channel": channel,
                "recipient": recipient,
                "failed_at": datetime.now(UTC),
                "error": error[:1000] if error else None,
            },
        )
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def list_for_alert(self, alert_id: int) -> list[dict[str, Any]]:
        if not await self._exists():
            return []
        query = text(
            """
            SELECT id, alert_id, channel, recipient,
                   delivered_at, failed_at, error,
                   acknowledged_by, created_at
            FROM alert_escalations
            WHERE alert_id = :alert_id
            ORDER BY created_at DESC, id DESC
            """
        )
        result = await self.db.execute(query, {"alert_id": alert_id})
        return [dict(row) for row in result.mappings().fetchall()]


__all__ = ["ALLOWED_CHANNELS", "AlertEscalationRepository", "Channel"]
