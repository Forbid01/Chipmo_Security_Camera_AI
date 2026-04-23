"""Data access for inference_metrics table.

Writes are idempotent per (camera_id, timestamp) via ON CONFLICT, so a
retried batch from an uploader cannot duplicate rows.

Reads cover the common analytics shapes: recent per camera, aggregated
per store (via cameras join), and a manual time-range delete until
TimescaleDB retention is wired up.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class InferenceMetricRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(
        self,
        *,
        camera_id: int,
        timestamp: datetime,
        fps: float | None = None,
        yolo_latency_ms: float | None = None,
        reid_latency_ms: float | None = None,
        rag_latency_ms: float | None = None,
        vlm_latency_ms: float | None = None,
        end_to_end_latency_ms: float | None = None,
    ) -> None:
        """Upsert a single per-camera metric sample."""
        timestamp = self._normalize_datetime(timestamp)
        query = text("""
            INSERT INTO inference_metrics (
                camera_id,
                timestamp,
                fps,
                yolo_latency_ms,
                reid_latency_ms,
                rag_latency_ms,
                vlm_latency_ms,
                end_to_end_latency_ms
            )
            VALUES (
                :camera_id,
                :timestamp,
                :fps,
                :yolo_latency_ms,
                :reid_latency_ms,
                :rag_latency_ms,
                :vlm_latency_ms,
                :end_to_end_latency_ms
            )
            ON CONFLICT (camera_id, timestamp) DO UPDATE
            SET fps                    = EXCLUDED.fps,
                yolo_latency_ms        = EXCLUDED.yolo_latency_ms,
                reid_latency_ms        = EXCLUDED.reid_latency_ms,
                rag_latency_ms         = EXCLUDED.rag_latency_ms,
                vlm_latency_ms         = EXCLUDED.vlm_latency_ms,
                end_to_end_latency_ms  = EXCLUDED.end_to_end_latency_ms
        """)
        await self.db.execute(
            query,
            {
                "camera_id": camera_id,
                "timestamp": timestamp,
                "fps": fps,
                "yolo_latency_ms": yolo_latency_ms,
                "reid_latency_ms": reid_latency_ms,
                "rag_latency_ms": rag_latency_ms,
                "vlm_latency_ms": vlm_latency_ms,
                "end_to_end_latency_ms": end_to_end_latency_ms,
            },
        )
        await self.db.commit()

    async def record_batch(
        self,
        samples: list[dict[str, Any]],
    ) -> int:
        """Upsert many samples in one transaction; returns count applied."""
        if not samples:
            return 0
        count = 0
        query = text("""
            INSERT INTO inference_metrics (
                camera_id,
                timestamp,
                fps,
                yolo_latency_ms,
                reid_latency_ms,
                rag_latency_ms,
                vlm_latency_ms,
                end_to_end_latency_ms
            )
            VALUES (
                :camera_id,
                :timestamp,
                :fps,
                :yolo_latency_ms,
                :reid_latency_ms,
                :rag_latency_ms,
                :vlm_latency_ms,
                :end_to_end_latency_ms
            )
            ON CONFLICT (camera_id, timestamp) DO UPDATE
            SET fps                    = EXCLUDED.fps,
                yolo_latency_ms        = EXCLUDED.yolo_latency_ms,
                reid_latency_ms        = EXCLUDED.reid_latency_ms,
                rag_latency_ms         = EXCLUDED.rag_latency_ms,
                vlm_latency_ms         = EXCLUDED.vlm_latency_ms,
                end_to_end_latency_ms  = EXCLUDED.end_to_end_latency_ms
        """)
        for sample in samples:
            await self.db.execute(
                query,
                {
                    "camera_id": sample["camera_id"],
                    "timestamp": self._normalize_datetime(sample["timestamp"]),
                    "fps": sample.get("fps"),
                    "yolo_latency_ms": sample.get("yolo_latency_ms"),
                    "reid_latency_ms": sample.get("reid_latency_ms"),
                    "rag_latency_ms": sample.get("rag_latency_ms"),
                    "vlm_latency_ms": sample.get("vlm_latency_ms"),
                    "end_to_end_latency_ms": sample.get("end_to_end_latency_ms"),
                },
            )
            count += 1
        await self.db.commit()
        return count

    async def get_recent_for_camera(
        self,
        camera_id: int,
        *,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT *
            FROM inference_metrics
            WHERE camera_id = :camera_id
            ORDER BY timestamp DESC
            LIMIT :limit
        """)
        result = await self.db.execute(
            query, {"camera_id": camera_id, "limit": limit}
        )
        return [dict(row) for row in result.mappings().fetchall()]

    async def aggregate_for_store(
        self,
        store_id: int,
        *,
        since: datetime,
        until: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Aggregate mean/p95 latency + fps across a store's cameras."""
        since = self._normalize_datetime(since)
        until = self._normalize_datetime(until) if until else datetime.now(UTC)
        query = text("""
            SELECT
                AVG(im.fps)                             AS avg_fps,
                AVG(im.end_to_end_latency_ms)           AS avg_e2e_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY im.end_to_end_latency_ms
                )                                        AS p95_e2e_ms,
                AVG(im.yolo_latency_ms)                 AS avg_yolo_ms,
                AVG(im.rag_latency_ms)                  AS avg_rag_ms,
                AVG(im.vlm_latency_ms)                  AS avg_vlm_ms,
                COUNT(*)                                 AS sample_count
            FROM inference_metrics im
            JOIN cameras c ON c.id = im.camera_id
            WHERE c.store_id = :store_id
              AND im.timestamp >= :since
              AND im.timestamp <  :until
        """)
        result = await self.db.execute(
            query,
            {"store_id": store_id, "since": since, "until": until},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Manual retention delete. Superseded by TimescaleDB policy when enabled."""
        cutoff = self._normalize_datetime(cutoff)
        query = text("""
            DELETE FROM inference_metrics
            WHERE timestamp < :cutoff
        """)
        result = await self.db.execute(query, {"cutoff": cutoff})
        await self.db.commit()
        return result.rowcount

    async def delete_older_than_days(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return await self.delete_older_than(cutoff)

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
