from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CaseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_case(
        self,
        *,
        store_id: int,
        camera_id: int | None = None,
        alert_id: int | None = None,
        timestamp: datetime | None = None,
        behavior_scores: dict[str, Any] | None = None,
        pose_sequence_path: str | None = None,
        clip_path: str | None = None,
        keyframe_paths: list[str] | None = None,
        label: str = "unlabeled",
        qdrant_point_id: UUID | None = None,
    ) -> dict[str, Any]:
        timestamp = self._normalize_datetime(timestamp) or datetime.now(UTC)
        query = text("""
            INSERT INTO cases (
                alert_id,
                store_id,
                camera_id,
                timestamp,
                behavior_scores,
                pose_sequence_path,
                clip_path,
                keyframe_paths,
                label,
                qdrant_point_id,
                updated_at
            )
            VALUES (
                :alert_id,
                :store_id,
                :camera_id,
                :timestamp,
                :behavior_scores,
                :pose_sequence_path,
                :clip_path,
                :keyframe_paths,
                :label,
                :qdrant_point_id,
                now()
            )
            RETURNING *
        """)
        result = await self.db.execute(
            query,
            {
                "alert_id": alert_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "timestamp": timestamp,
                "behavior_scores": behavior_scores or {},
                "pose_sequence_path": pose_sequence_path,
                "clip_path": clip_path,
                "keyframe_paths": keyframe_paths or [],
                "label": label,
                "qdrant_point_id": qdrant_point_id,
            },
        )
        await self.db.commit()
        return dict(result.mappings().fetchone())

    async def get_by_id(self, case_id: UUID | str) -> dict[str, Any] | None:
        result = await self.db.execute(
            text("SELECT * FROM cases WHERE id = :id"),
            {"id": case_id},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_by_alert_id(self, alert_id: int) -> dict[str, Any] | None:
        result = await self.db.execute(
            text("SELECT * FROM cases WHERE alert_id = :alert_id ORDER BY created_at DESC LIMIT 1"),
            {"alert_id": alert_id},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def list_unlabeled(
        self,
        *,
        store_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            text("""
                SELECT *
                FROM cases
                WHERE store_id = :store_id
                  AND (label IS NULL OR label = 'unlabeled')
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            {"store_id": store_id, "limit": limit},
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def update_label(
        self,
        *,
        case_id: UUID | str,
        label: str,
        label_confidence: float | None = None,
        labeled_by: int | None = None,
        labeled_at: datetime | None = None,
    ) -> bool:
        labeled_at = self._normalize_datetime(labeled_at) or datetime.now(UTC)
        result = await self.db.execute(
            text("""
                UPDATE cases
                SET label = :label,
                    label_confidence = :label_confidence,
                    labeled_by = :labeled_by,
                    labeled_at = :labeled_at,
                    updated_at = now()
                WHERE id = :id
            """),
            {
                "id": case_id,
                "label": label,
                "label_confidence": label_confidence,
                "labeled_by": labeled_by,
                "labeled_at": labeled_at,
            },
        )
        await self.db.commit()
        return result.rowcount > 0

    async def update_vlm_verdict(
        self,
        *,
        case_id: UUID | str,
        is_suspicious: bool,
        confidence: float,
        reason: str | None,
        run_at: datetime | None = None,
    ) -> bool:
        run_at = self._normalize_datetime(run_at) or datetime.now(UTC)
        result = await self.db.execute(
            text("""
                UPDATE cases
                SET vlm_is_suspicious = :is_suspicious,
                    vlm_confidence = :confidence,
                    vlm_reason = :reason,
                    vlm_run_at = :run_at,
                    updated_at = now()
                WHERE id = :id
            """),
            {
                "id": case_id,
                "is_suspicious": is_suspicious,
                "confidence": confidence,
                "reason": reason,
                "run_at": run_at,
            },
        )
        await self.db.commit()
        return result.rowcount > 0

    async def attach_qdrant_point(
        self,
        *,
        case_id: UUID | str,
        qdrant_point_id: UUID,
    ) -> bool:
        result = await self.db.execute(
            text("""
                UPDATE cases
                SET qdrant_point_id = :qdrant_point_id,
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": case_id, "qdrant_point_id": qdrant_point_id},
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
