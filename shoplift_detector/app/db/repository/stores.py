import json
import logging
from typing import Any

from app.schemas.store import StoreCreate, StoreUpdate
from app.schemas.store_settings import (
    StoreSettings,
    StoreSettingsPatch,
    default_settings_payload,
    resolve_settings,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class StoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._has_settings_column: bool | None = None

    async def _settings_column_exists(self) -> bool:
        if self._has_settings_column is None:
            query = text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'stores'
                  AND column_name = 'settings'
                LIMIT 1
            """)
            result = await self.db.execute(query)
            self._has_settings_column = result.fetchone() is not None
        return self._has_settings_column

    @staticmethod
    def _coerce_settings_blob(raw: Any) -> dict[str, Any] | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("stores.settings contained invalid JSON; using defaults")
                return None
        return None

    async def create(self, data: StoreCreate) -> int | None:
        columns = ["name", "address", "organization_id", "alert_threshold", "alert_cooldown"]
        params = {
            "name": data.name, "address": data.address,
            "org_id": data.organization_id, "threshold": data.alert_threshold,
            "cooldown": data.alert_cooldown,
        }
        placeholders = [":name", ":address", ":org_id", ":threshold", ":cooldown"]

        if data.telegram_chat_id is not None:
            columns.append("telegram_chat_id")
            placeholders.append(":telegram_chat_id")
            params["telegram_chat_id"] = data.telegram_chat_id

        query = text(f"""
            INSERT INTO stores ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING id
        """)
        result = await self.db.execute(query, params)
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

    async def update(
        self,
        store_id: int,
        data: StoreUpdate,
        *,
        organization_id: int | None = None,
    ) -> bool:
        """T02-22: optional tenant pin. Supplying `organization_id`
        adds `AND organization_id = :org_id` to the WHERE. `None`
        preserves super-admin paths that operate across tenants.
        """
        updates = []
        params: dict[str, Any] = {"id": store_id}
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
            f"UPDATE stores SET {', '.join(updates)} "
            f"WHERE id = :id{tenant_clause}"
        )
        result = await self.db.execute(query, params)
        await self.db.commit()
        return result.rowcount > 0

    async def delete(
        self,
        store_id: int,
        *,
        organization_id: int | None = None,
    ) -> bool:
        params: dict[str, Any] = {"id": store_id}
        tenant_clause = ""
        if organization_id is not None:
            tenant_clause = " AND organization_id = :org_id"
            params["org_id"] = organization_id
        query = text(f"DELETE FROM stores WHERE id = :id{tenant_clause}")
        result = await self.db.execute(query, params)
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

    async def get_settings(self, store_id: int) -> StoreSettings:
        """Resolved StoreSettings буцаана (stored payload + defaults).

        - Store байхгүй → defaults
        - `settings` column байхгүй → legacy `alert_threshold`/`alert_cooldown`
          баганаас үндэслэж defaults дээр overlay хийнэ.
        """
        if not await self._settings_column_exists():
            query = text("""
                SELECT alert_threshold, alert_cooldown, telegram_chat_id
                FROM stores WHERE id = :id
            """)
            result = await self.db.execute(query, {"id": store_id})
            row = result.mappings().fetchone()
            if not row:
                return StoreSettings()
            payload = default_settings_payload()
            payload["alert_threshold"] = float(row.get("alert_threshold") or 80.0)
            payload["alert_cooldown_seconds"] = int(row.get("alert_cooldown") or 60)
            chat_id = row.get("telegram_chat_id")
            if chat_id:
                payload["notification_channels"]["telegram"]["chat_ids"] = [chat_id]
            return resolve_settings(payload)

        query = text("""
            SELECT settings, alert_threshold, alert_cooldown, telegram_chat_id
            FROM stores WHERE id = :id
        """)
        result = await self.db.execute(query, {"id": store_id})
        row = result.mappings().fetchone()
        if not row:
            return StoreSettings()

        stored = self._coerce_settings_blob(row.get("settings"))
        if stored:
            return resolve_settings(stored)

        payload = default_settings_payload()
        payload["alert_threshold"] = float(row.get("alert_threshold") or 80.0)
        payload["alert_cooldown_seconds"] = int(row.get("alert_cooldown") or 60)
        chat_id = row.get("telegram_chat_id")
        if chat_id:
            payload["notification_channels"]["telegram"]["chat_ids"] = [chat_id]
        return resolve_settings(payload)

    async def update_settings(
        self,
        store_id: int,
        patch: StoreSettingsPatch,
    ) -> StoreSettings:
        """Merge `patch` onto current settings and persist.

        Returns the resolved StoreSettings after write. Dual-writes the
        legacy `alert_threshold`/`alert_cooldown` columns so legacy code
        paths keep working during the expand → contract window.
        """
        if not await self._settings_column_exists():
            raise RuntimeError(
                "stores.settings column missing — run alembic migration 20260421_01"
            )

        current = await self.get_settings(store_id)
        merged_dict = current.model_dump(mode="json")
        for field, value in patch.model_dump(mode="json", exclude_unset=True).items():
            merged_dict[field] = value
        merged = resolve_settings(merged_dict)
        merged_payload = merged.model_dump(mode="json")

        params = {
            "id": store_id,
            "settings": json.dumps(merged_payload),
            "alert_threshold": merged.alert_threshold,
            "alert_cooldown": merged.alert_cooldown_seconds,
        }
        query = text("""
            UPDATE stores
            SET settings = CAST(:settings AS JSONB),
                alert_threshold = :alert_threshold,
                alert_cooldown = :alert_cooldown
            WHERE id = :id
        """)
        await self.db.execute(query, params)
        await self.db.commit()
        return merged
