import json
import logging
from typing import Any

from app.schemas.camera import CameraCreate, CameraUpdate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CameraRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: CameraCreate) -> int | None:
        query = text("""
            INSERT INTO cameras (name, url, camera_type, store_id, is_ai_enabled, organization_id, substream_url)
            VALUES (:name, :url, :type, :store_id, :ai, :org_id, :substream_url)
            RETURNING id
        """)
        result = await self.db.execute(query, {
            "name": data.name, "url": data.url, "type": data.camera_type,
            "store_id": data.store_id, "ai": data.is_ai_enabled,
            "org_id": data.organization_id,
            "substream_url": getattr(data, "substream_url", None),
        })
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_all(self) -> list[dict[str, Any]]:
        query = text("""
            SELECT c.*, o.name as organization_name, s.name as store_name
            FROM cameras c
            LEFT JOIN organizations o ON c.organization_id = o.id
            LEFT JOIN stores s ON c.store_id = s.id
            ORDER BY c.created_at DESC
        """)
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def get_by_store(self, store_id: int) -> list[dict[str, Any]]:
        query = text("""
            SELECT c.*, s.name as store_name
            FROM cameras c
            LEFT JOIN stores s ON c.store_id = s.id
            WHERE c.store_id = :store_id AND c.is_active = TRUE
            ORDER BY c.created_at DESC
        """)
        result = await self.db.execute(query, {"store_id": store_id})
        return [dict(row) for row in result.mappings().fetchall()]

    async def get_by_organization(self, org_id: int) -> list[dict[str, Any]]:
        query = text("""
            SELECT c.*, s.name as store_name, o.name as organization_name
            FROM cameras c
            LEFT JOIN stores s ON c.store_id = s.id
            LEFT JOIN organizations o ON c.organization_id = o.id
            WHERE c.organization_id = :org_id AND c.is_active = TRUE
            ORDER BY c.created_at DESC
        """)
        result = await self.db.execute(query, {"org_id": org_id})
        return [dict(row) for row in result.mappings().fetchall()]

    async def get_active_cameras(self) -> list[dict[str, Any]]:
        """AI болон camera service-д зориулсан - бүх идэвхтэй камерууд."""
        query = text("""
            SELECT c.*, s.name as store_name, s.alert_threshold, s.alert_cooldown
            FROM cameras c
            LEFT JOIN stores s ON c.store_id = s.id
            WHERE c.is_active = TRUE
            ORDER BY c.store_id, c.id
        """)
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def update(
        self,
        camera_id: int,
        data: CameraUpdate,
        *,
        organization_id: int | None = None,
    ) -> bool:
        """T02-22: optional tenant pin. When `organization_id` is
        supplied (the T02-21 handler path does), the UPDATE's WHERE
        clause includes `cameras.organization_id = :org_id` so a mis-wired
        handler cannot UPDATE another tenant's row. `None` keeps legacy
        super-admin paths working.
        """
        updates = []
        params: dict[str, Any] = {"id": camera_id}
        for field, value in data.model_dump(exclude_unset=True).items():
            updates.append(f"{field} = :{field}")
            params[field] = value

        if not updates:
            return True

        tenant_clause = ""
        if organization_id is not None:
            tenant_clause = " AND organization_id = :org_id"
            params["org_id"] = organization_id

        query = text(
            f"UPDATE cameras SET {', '.join(updates)} "
            f"WHERE id = :id{tenant_clause}"
        )
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

    async def delete(
        self,
        camera_id: int,
        *,
        organization_id: int | None = None,
    ) -> bool:
        params: dict[str, Any] = {"id": camera_id}
        tenant_clause = ""
        if organization_id is not None:
            tenant_clause = " AND organization_id = :org_id"
            params["org_id"] = organization_id
        query = text(
            f"DELETE FROM cameras WHERE id = :id{tenant_clause}"
        )
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

    async def get_shelf_zones(
        self,
        camera_id: int,
        *,
        organization_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"id": camera_id}
        tenant_clause = ""
        if organization_id is not None:
            tenant_clause = " AND organization_id = :org_id"
            params["org_id"] = organization_id
        query = text(
            f"SELECT shelf_zones FROM cameras WHERE id = :id{tenant_clause}"
        )
        result = await self.db.execute(query, params)
        row = result.fetchone()
        if row is None:
            return []
        zones = row[0]
        if isinstance(zones, str):
            try:
                zones = json.loads(zones)
            except json.JSONDecodeError:
                logger.warning(
                    "camera_shelf_zones_malformed_json",
                    extra={"camera_id": camera_id},
                )
                return []
        return zones or []

    async def update_shelf_zones(
        self,
        camera_id: int,
        zones: list[dict[str, Any]],
        *,
        organization_id: int | None = None,
    ) -> bool:
        """Replace the full shelf_zones array for a camera.

        Tenant pin (`organization_id`) prevents a mis-wired admin handler
        from overwriting another tenant's zones — same pattern as `update`.
        """
        params: dict[str, Any] = {
            "id": camera_id,
            "zones": json.dumps(zones),
        }
        tenant_clause = ""
        if organization_id is not None:
            tenant_clause = " AND organization_id = :org_id"
            params["org_id"] = organization_id
        query = text(
            f"UPDATE cameras SET shelf_zones = CAST(:zones AS JSONB) "
            f"WHERE id = :id{tenant_clause}"
        )
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0
