"""Data access for sync_packs table.

Tracks version/status/signature lifecycle of sync packs published per store.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.db.models.sync_pack import SYNC_PACK_STATUSES
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TERMINAL_STATUSES: frozenset[str] = frozenset({"applied", "failed", "rolled_back"})


class SyncPackRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in SYNC_PACK_STATUSES:
            raise ValueError(
                f"Invalid sync_pack status '{status}'. "
                f"Allowed: {', '.join(SYNC_PACK_STATUSES)}"
            )

    async def create(
        self,
        *,
        store_id: int,
        version: str,
        weights_hash: str | None = None,
        qdrant_snapshot_id: str | None = None,
        case_count: int | None = None,
        s3_path: str | None = None,
        signature: str | None = None,
    ) -> dict[str, Any]:
        query = text("""
            INSERT INTO sync_packs (
                store_id,
                version,
                weights_hash,
                qdrant_snapshot_id,
                case_count,
                s3_path,
                signature,
                status
            )
            VALUES (
                :store_id,
                :version,
                :weights_hash,
                :qdrant_snapshot_id,
                :case_count,
                :s3_path,
                :signature,
                'pending'
            )
            RETURNING id, store_id, version, weights_hash,
                      qdrant_snapshot_id, case_count, s3_path, signature,
                      status, applied_at,
                      created_at, updated_at
        """)
        result = await self.db.execute(
            query,
            {
                "store_id": store_id,
                "version": version,
                "weights_hash": weights_hash,
                "qdrant_snapshot_id": qdrant_snapshot_id,
                "case_count": case_count,
                "s3_path": s3_path,
                "signature": signature,
            },
        )
        await self.db.commit()
        row = result.mappings().fetchone()
        return dict(row)

    async def get_by_id(
        self, sync_pack_id: UUID | str
    ) -> dict[str, Any] | None:
        query = text("""
            SELECT *
            FROM sync_packs
            WHERE id = CAST(:id AS UUID)
            LIMIT 1
        """)
        result = await self.db.execute(query, {"id": str(sync_pack_id)})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_latest_for_store(
        self, store_id: int
    ) -> dict[str, Any] | None:
        """Latest pack (any status) created for a store."""
        query = text("""
            SELECT *
            FROM sync_packs
            WHERE store_id = :store_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = await self.db.execute(query, {"store_id": store_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_latest_applied_for_store(
        self, store_id: int
    ) -> dict[str, Any] | None:
        """Most recent successfully applied pack for a store."""
        query = text("""
            SELECT *
            FROM sync_packs
            WHERE store_id = :store_id
              AND status = 'applied'
            ORDER BY applied_at DESC NULLS LAST, created_at DESC
            LIMIT 1
        """)
        result = await self.db.execute(query, {"store_id": store_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def list_for_store(
        self,
        store_id: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT *
            FROM sync_packs
            WHERE store_id = :store_id
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        result = await self.db.execute(
            query, {"store_id": store_id, "limit": limit}
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def mark_downloaded(
        self,
        sync_pack_id: UUID | str,
    ) -> bool:
        query = text("""
            UPDATE sync_packs
            SET status = 'downloaded'
            WHERE id = CAST(:id AS UUID)
              AND status = 'pending'
        """)
        result = await self.db.execute(
            query,
            {"id": str(sync_pack_id)},
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_applied(
        self,
        sync_pack_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        query = text("""
            UPDATE sync_packs
            SET status = 'applied',
                applied_at = :now
            WHERE id = CAST(:id AS UUID)
              AND status IN ('pending', 'downloaded')
        """)
        result = await self.db.execute(
            query,
            {
                "id": str(sync_pack_id),
                "now": now,
            },
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_failed(self, sync_pack_id: UUID | str) -> bool:
        return await self._set_terminal_status(sync_pack_id, "failed")

    async def mark_rolled_back(self, sync_pack_id: UUID | str) -> bool:
        return await self._set_terminal_status(sync_pack_id, "rolled_back")

    async def update_status(
        self,
        sync_pack_id: UUID | str,
        status: str,
    ) -> bool:
        self._validate_status(status)
        query = text("""
            UPDATE sync_packs
            SET status = :status
            WHERE id = CAST(:id AS UUID)
        """)
        result = await self.db.execute(
            query, {"id": str(sync_pack_id), "status": status}
        )
        await self.db.commit()
        return result.rowcount > 0

    async def _set_terminal_status(
        self,
        sync_pack_id: UUID | str,
        status: str,
    ) -> bool:
        self._validate_status(status)
        query = text("""
            UPDATE sync_packs
            SET status = :status
            WHERE id = CAST(:id AS UUID)
              AND status NOT IN ('applied', 'failed', 'rolled_back')
        """)
        result = await self.db.execute(
            query, {"id": str(sync_pack_id), "status": status}
        )
        await self.db.commit()
        return result.rowcount > 0
