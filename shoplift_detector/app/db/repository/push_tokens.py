"""Push-token registry (T5-07).

One row per (user, device). `token` is uppercase UNIQUE so the same
device re-registering doesn't duplicate. The FCM dispatcher asks this
repo which tokens to fan out to for a given store's managers.

Pre-migration safe: every read returns `[]` and every write no-ops.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Platform = Literal["ios", "android", "web"]
ALLOWED_PLATFORMS: frozenset[str] = frozenset({"ios", "android", "web"})


class PushTokenRepository:
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
                WHERE table_schema = 'public' AND table_name = 'push_tokens'
            )
            """
        )
        try:
            result = await self.db.execute(query)
            self._table_exists = bool(result.scalar())
        except ProgrammingError:
            self._table_exists = False
        return self._table_exists

    async def register(
        self,
        *,
        user_id: int,
        token: str,
        platform: Platform,
    ) -> int | None:
        if platform not in ALLOWED_PLATFORMS:
            raise ValueError(
                f"platform must be one of {sorted(ALLOWED_PLATFORMS)}: {platform!r}"
            )
        if not token.strip():
            raise ValueError("token must not be empty")
        if not await self._exists():
            return None
        query = text(
            """
            INSERT INTO push_tokens (user_id, token, platform)
            VALUES (:user_id, :token, :platform)
            ON CONFLICT (token) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    platform = EXCLUDED.platform,
                    last_seen_at = now()
            RETURNING id
            """
        )
        result = await self.db.execute(
            query,
            {"user_id": user_id, "token": token.strip(), "platform": platform},
        )
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def unregister(self, token: str) -> bool:
        if not await self._exists():
            return False
        query = text("DELETE FROM push_tokens WHERE token = :token")
        result = await self.db.execute(query, {"token": token})
        await self.db.commit()
        return result.rowcount > 0

    async def list_for_store(self, store_id: int) -> list[dict[str, Any]]:
        """All active push tokens for any user that manages the store.

        Joined through `store_telegram_subscribers` as a proxy for
        "user cares about this store" until a dedicated `store_users`
        pivot lands. Falls back to an empty list pre-migration.
        """
        if not await self._exists():
            return []
        query = text(
            """
            SELECT pt.id, pt.user_id, pt.token, pt.platform
            FROM push_tokens pt
            WHERE pt.user_id IN (
                SELECT u.id FROM users u
                WHERE u.organization_id = (
                    SELECT organization_id FROM stores WHERE id = :store_id
                )
            )
            """
        )
        result = await self.db.execute(query, {"store_id": store_id})
        return [dict(row) for row in result.mappings().fetchall()]


__all__ = ["ALLOWED_PLATFORMS", "Platform", "PushTokenRepository"]
