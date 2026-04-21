from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_camera_id(camera_id: int | None) -> int:
    return int(camera_id or 0)


class AlertStateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_state(
        self,
        *,
        camera_id: int | None,
        person_track_id: int,
    ) -> dict[str, Any] | None:
        query = text("""
            SELECT
                id,
                camera_id,
                person_track_id,
                state,
                last_alert_id,
                last_alert_at,
                cooldown_until,
                resolved_at,
                created_at,
                updated_at
            FROM alert_state
            WHERE camera_id = :camera_id
              AND person_track_id = :person_track_id
            LIMIT 1
        """)
        result = await self.db.execute(
            query,
            {
                "camera_id": normalize_camera_id(camera_id),
                "person_track_id": person_track_id,
            },
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def upsert_state(
        self,
        *,
        camera_id: int | None,
        person_track_id: int,
        state: str,
        last_alert_id: int | None = None,
        last_alert_at: datetime | None = None,
        cooldown_until: datetime | None = None,
        resolved_at: datetime | None = None,
    ) -> dict[str, Any]:
        query = text("""
            INSERT INTO alert_state (
                camera_id,
                person_track_id,
                state,
                last_alert_id,
                last_alert_at,
                cooldown_until,
                resolved_at,
                updated_at
            )
            VALUES (
                :camera_id,
                :person_track_id,
                :state,
                :last_alert_id,
                :last_alert_at,
                :cooldown_until,
                :resolved_at,
                now()
            )
            ON CONFLICT (camera_id, person_track_id) DO UPDATE SET
                state = EXCLUDED.state,
                last_alert_id = COALESCE(EXCLUDED.last_alert_id, alert_state.last_alert_id),
                last_alert_at = COALESCE(EXCLUDED.last_alert_at, alert_state.last_alert_at),
                cooldown_until = EXCLUDED.cooldown_until,
                resolved_at = EXCLUDED.resolved_at,
                updated_at = now()
            RETURNING
                id,
                camera_id,
                person_track_id,
                state,
                last_alert_id,
                last_alert_at,
                cooldown_until,
                resolved_at,
                created_at,
                updated_at
        """)
        params = {
            "camera_id": normalize_camera_id(camera_id),
            "person_track_id": person_track_id,
            "state": state,
            "last_alert_id": last_alert_id,
            "last_alert_at": self._normalize_datetime(last_alert_at),
            "cooldown_until": self._normalize_datetime(cooldown_until),
            "resolved_at": self._normalize_datetime(resolved_at),
        }
        result = await self.db.execute(query, params)
        await self.db.commit()
        row = result.mappings().fetchone()
        return dict(row) if row else params

    async def mark_active(
        self,
        *,
        camera_id: int | None,
        person_track_id: int,
        now: datetime,
        cooldown_until: datetime,
    ) -> dict[str, Any]:
        return await self.upsert_state(
            camera_id=camera_id,
            person_track_id=person_track_id,
            state="active",
            last_alert_at=now,
            cooldown_until=cooldown_until,
            resolved_at=None,
        )

    async def mark_cooldown(
        self,
        *,
        camera_id: int | None,
        person_track_id: int,
        alert_id: int | None,
        last_alert_at: datetime,
        cooldown_until: datetime,
    ) -> dict[str, Any]:
        return await self.upsert_state(
            camera_id=camera_id,
            person_track_id=person_track_id,
            state="cooldown",
            last_alert_id=alert_id,
            last_alert_at=last_alert_at,
            cooldown_until=cooldown_until,
            resolved_at=None,
        )

    async def mark_resolved(
        self,
        *,
        camera_id: int | None,
        person_track_id: int,
        resolved_at: datetime | None = None,
    ) -> dict[str, Any]:
        resolved_at = self._normalize_datetime(resolved_at) or datetime.now(UTC)
        return await self.upsert_state(
            camera_id=camera_id,
            person_track_id=person_track_id,
            state="resolved",
            cooldown_until=None,
            resolved_at=resolved_at,
        )

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
