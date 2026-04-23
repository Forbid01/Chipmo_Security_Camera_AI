from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InferenceMetric(Base):
    """Per-camera FPS / stage-latency data point.

    Composite PK (camera_id, timestamp) keeps rows unique without
    requiring a synthetic id.

    TimescaleDB hypertable conversion is deferred; this table behaves as
    a normal PostgreSQL table until then.
    """

    __tablename__ = "inference_metrics"

    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        primary_key=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )

    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    yolo_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reid_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rag_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    vlm_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_to_end_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<InferenceMetric(camera_id={self.camera_id}, "
            f"timestamp={self.timestamp.isoformat() if self.timestamp else None}, "
            f"fps={self.fps})>"
        )
