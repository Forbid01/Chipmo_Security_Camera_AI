import logging
from typing import Any

from app.schemas.store import StoreCreate, StoreUpdate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class StoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: StoreCreate) -> int | None:
        query = text("""
            INSERT INTO stores (name, address, organization_id, alert_threshold, alert_cooldown, telegram_chat_id)
            VALUES (:name, :address, :org_id, :threshold, :cooldown, :telegram_chat_id)
            RETURNING id
        """)
        result = await self.db.execute(query, {
            "name": data.name, "address": data.address,
            "org_id": data.organization_id, "threshold": data.alert_threshold,
            "cooldown": data.alert_cooldown, "telegram_chat_id": data.telegram_chat_id,
        })
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_by_id(self, store_id: int) -> dict[str, Any] | None:
        query = text("""
            SELECT s.*, o.name as organization_name,
                   (SELECT COUNT(*) FROM cameras c WHERE c.store_id = s.id) as camera_count
            FROM stores s
            LEFT JOIN organizations o ON s.organization_id = o.id
            WHERE s.id = :id
        """)
        result = await self.db.execute(query, {"id": store_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_all(self) -> list[dict[str, Any]]:
        query = text("""
            SELECT s.*, o.name as organization_name,
                   (SELECT COUNT(*) FROM cameras c WHERE c.store_id = s.id) as camera_count
            FROM stores s
            LEFT JOIN organizations o ON s.organization_id = o.id
            ORDER BY s.created_at DESC
        """)
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def get_by_organization(self, org_id: int) -> list[dict[str, Any]]:
        query = text("""
            SELECT s.*, o.name as organization_name,
                   (SELECT COUNT(*) FROM cameras c WHERE c.store_id = s.id) as camera_count
            FROM stores s
            LEFT JOIN organizations o ON s.organization_id = o.id
            WHERE s.organization_id = :org_id
            ORDER BY s.created_at DESC
        """)
        result = await self.db.execute(query, {"org_id": org_id})
        return [dict(row) for row in result.mappings().fetchall()]

    async def update(self, store_id: int, data: StoreUpdate) -> bool:
        updates = []
        params = {"id": store_id}
        for field, value in data.model_dump(exclude_unset=True).items():
            updates.append(f"{field} = :{field}")
            params[field] = value

        if not updates:
            return True

        query = text(f"UPDATE stores SET {', '.join(updates)} WHERE id = :id")
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

    async def delete(self, store_id: int) -> bool:
        query = text("DELETE FROM stores WHERE id = :id")
        result = await self.db.execute(query, {"id": store_id})
        await self.db.commit()
        return result.rowcount > 0

    async def count(self) -> int:
        query = text("SELECT COUNT(*) FROM stores")
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_threshold(self, store_id: int) -> float:
        """Дэлгүүрийн AI threshold авах (auto-learning-д ашиглана)."""
        query = text("SELECT alert_threshold FROM stores WHERE id = :id")
        result = await self.db.execute(query, {"id": store_id})
        row = result.fetchone()
        return row[0] if row else 80.0
