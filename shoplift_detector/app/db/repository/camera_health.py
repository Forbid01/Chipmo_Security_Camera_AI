from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CameraHealthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_heartbeat(
        self,
        *,
        camera_id: int,
        store_id: int | None,
        status: str,
        is_connected: bool,
        fps: float,
        last_frame_at: datetime | None,
        last_error: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = self._normalize_datetime(now) or datetime.now(UTC)
        last_frame_at = self._normalize_datetime(last_frame_at)
        offline_since = now if status in {"offline", "degraded"} else None
        query = text("""
            INSERT INTO camera_health (
                camera_id,
                store_id,
                status,
                is_connected,
                fps,
                last_frame_at,
                last_heartbeat_at,
                offline_since,
                last_error,
                updated_at
            )
            VALUES (
                :camera_id,
                :store_id,
                :status,
                :is_connected,
                :fps,
                :last_frame_at,
                :last_heartbeat_at,
                :offline_since,
                :last_error,
                now()
            )
            ON CONFLICT (camera_id) DO UPDATE SET
                store_id = EXCLUDED.store_id,
                status = EXCLUDED.status,
                is_connected = EXCLUDED.is_connected,
                fps = EXCLUDED.fps,
                last_frame_at = EXCLUDED.last_frame_at,
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                offline_since = CASE
                    WHEN EXCLUDED.status IN ('offline', 'degraded')
                        THEN COALESCE(camera_health.offline_since, EXCLUDED.offline_since)
                    ELSE NULL
                END,
                last_error = EXCLUDED.last_error,
                updated_at = now()
            RETURNING
                camera_id,
                store_id,
                status,
                is_connected,
                fps,
                last_frame_at,
                last_heartbeat_at,
                offline_since,
                last_error,
                last_notification_at,
                created_at,
                updated_at
        """)
        params = {
            "camera_id": camera_id,
            "store_id": store_id,
            "status": status,
            "is_connected": is_connected,
            "fps": fps,
            "last_frame_at": last_frame_at,
            "last_heartbeat_at": now,
            "offline_since": offline_since,
            "last_error": last_error,
        }
        result = await self.db.execute(query, params)
        await self.db.commit()
        row = result.mappings().fetchone()
        return dict(row) if row else params

    async def get_offline_for_notification(
        self,
        *,
        offline_for_seconds: int,
        notification_interval_seconds: int,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = self._normalize_datetime(now) or datetime.now(UTC)
        offline_before = now - timedelta(seconds=offline_for_seconds)
        notify_before = now - timedelta(seconds=notification_interval_seconds)
        query = text("""
            SELECT
                camera_id,
                store_id,
                status,
                offline_since,
                last_notification_at,
                last_error
            FROM camera_health
            WHERE status = 'offline'
              AND offline_since <= :offline_before
              AND (
                last_notification_at IS NULL
                OR last_notification_at <= :notify_before
              )
        """)
        result = await self.db.execute(
            query,
            {
                "offline_before": offline_before,
                "notify_before": notify_before,
            },
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def mark_notification_sent(
        self,
        *,
        camera_id: int,
        notified_at: datetime | None = None,
    ) -> bool:
        notified_at = self._normalize_datetime(notified_at) or datetime.now(UTC)
        query = text("""
            UPDATE camera_health
            SET last_notification_at = :notified_at,
                updated_at = now()
            WHERE camera_id = :camera_id
        """)
        result = await self.db.execute(
            query,
            {"camera_id": camera_id, "notified_at": notified_at},
        )
        await self.db.commit()
        return result.rowcount > 0

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
