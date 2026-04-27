"""Telegram subscribers per store (T5-04).

The legacy `stores.telegram_chat_id` holds a single chat_id per store.
T5-04 replaces that with a many-to-one mapping — multiple managers /
owners / staff subscribe and each gets the alert. The table also
carries a `role` column so higher-severity alerts can later be routed
only to owners (T5-05+).

Schema — `store_telegram_subscribers`:

    id          SERIAL PRIMARY KEY
    store_id    INTEGER NOT NULL FK stores(id) ON DELETE CASCADE
    chat_id     TEXT NOT NULL
    role        TEXT NOT NULL DEFAULT 'manager'
                CHECK (role IN ('owner', 'manager', 'staff'))
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    UNIQUE (store_id, chat_id)

Every method tolerates a pre-migration database by returning an empty
list / no-op. That lets the alert fan-out path (`ai_service._send_telegram_alert`)
call this repo unconditionally; before the migration runs it simply
falls through to the legacy `stores.telegram_chat_id` path.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


ALLOWED_ROLES: frozenset[str] = frozenset({"owner", "manager", "staff"})


class TelegramSubscriberRepository:
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
                  AND table_name = 'store_telegram_subscribers'
            )
            """
        )
        try:
            result = await self.db.execute(query)
            self._table_exists = bool(result.scalar())
        except ProgrammingError:
            # Older Postgres lacks information_schema visibility for the
            # role — treat as "not here" so callers fall through.
            self._table_exists = False
        return self._table_exists

    async def list_for_store(self, store_id: int) -> list[dict[str, Any]]:
        """All subscribers for a store, oldest first (stable ordering).

        Returns an empty list on the pre-migration schema so the alert
        fan-out can gracefully fall back to `stores.telegram_chat_id`.
        """
        if not await self._exists():
            return []
        query = text(
            """
            SELECT id, store_id, chat_id, role, created_at
            FROM store_telegram_subscribers
            WHERE store_id = :store_id
            ORDER BY created_at ASC, id ASC
            """
        )
        result = await self.db.execute(query, {"store_id": store_id})
        return [dict(row) for row in result.mappings().fetchall()]

    async def add(
        self,
        *,
        store_id: int,
        chat_id: str,
        role: str = "manager",
    ) -> int | None:
        """Idempotent subscribe. Returns the row id on insert, None on
        the pre-migration schema or if (store_id, chat_id) already exists."""
        if role not in ALLOWED_ROLES:
            raise ValueError(f"role must be one of {sorted(ALLOWED_ROLES)}: {role!r}")
        if not await self._exists():
            return None
        query = text(
            """
            INSERT INTO store_telegram_subscribers (store_id, chat_id, role)
            VALUES (:store_id, :chat_id, :role)
            ON CONFLICT (store_id, chat_id) DO UPDATE
                SET role = EXCLUDED.role
            RETURNING id
            """
        )
        result = await self.db.execute(
            query,
            {"store_id": store_id, "chat_id": chat_id, "role": role},
        )
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def remove(self, *, store_id: int, chat_id: str) -> bool:
        if not await self._exists():
            return False
        query = text(
            """
            DELETE FROM store_telegram_subscribers
            WHERE store_id = :store_id AND chat_id = :chat_id
            """
        )
        result = await self.db.execute(
            query,
            {"store_id": store_id, "chat_id": chat_id},
        )
        await self.db.commit()
        return result.rowcount > 0

    async def find_by_chat(self, chat_id: str) -> list[dict[str, Any]]:
        """Reverse lookup — which stores is this chat subscribed to?

        Used by the bot's `/status` handler so a user who DM'd the bot
        can see all the stores they receive alerts for.
        """
        if not await self._exists():
            return []
        query = text(
            """
            SELECT s.id AS store_id, s.name AS store_name, sub.role
            FROM store_telegram_subscribers sub
            JOIN stores s ON s.id = sub.store_id
            WHERE sub.chat_id = :chat_id
            ORDER BY s.name ASC
            """
        )
        result = await self.db.execute(query, {"chat_id": chat_id})
        return [dict(row) for row in result.mappings().fetchall()]


__all__ = ["ALLOWED_ROLES", "TelegramSubscriberRepository"]
