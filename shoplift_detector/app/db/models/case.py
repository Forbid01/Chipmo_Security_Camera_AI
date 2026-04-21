from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CaseRecord(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(
            "label IN ('theft', 'false_positive', 'not_sure', 'unlabeled')",
            name="ck_cases_label",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    behavior_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    pose_sequence_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    keyframe_paths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    label: Mapped[str] = mapped_column(String(32), default="unlabeled", nullable=False)
    label_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    labeled_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vlm_is_suspicious: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vlm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    vlm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    vlm_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    qdrant_point_id: Mapped[UUID | None] = mapped_column(nullable=True, unique=True)

    def __repr__(self) -> str:
        return f"<CaseRecord(id={self.id}, store_id={self.store_id}, label='{self.label}')>"
