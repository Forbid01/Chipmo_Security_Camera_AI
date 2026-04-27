from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .alert_feedback import AlertFeedback
    from .camera import Camera
    from .organization import Organization
    from .store import Store


# Decision values allowed in the RAG / VLM pipeline columns. These are
# not DB-enforced (both columns are plain VARCHAR so a future stage can
# ship a new verdict without a schema change), but keeping constants
# here stops the raw strings from drifting across services.
RAG_DECISIONS = ("not_run", "passed", "suppressed_by_rag")
VLM_DECISIONS = ("not_run", "passed", "suppressed_by_vlm")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Auto-learning: true_positive, false_positive, unreviewed
    feedback_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)

    # --- Pipeline v2 columns (T02-14) --------------------------------------
    # True when the alert was produced but did not reach the customer
    # because the RAG or VLM layer rejected it. We keep suppressed rows
    # so dashboards can chart suppression rate and so regressions in
    # the layered pipeline are visible.
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppressed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RAG / VLM verdicts. See RAG_DECISIONS / VLM_DECISIONS above.
    rag_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vlm_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Tracker id emitted by ByteTrack, distinct from legacy `person_id`
    # (which callers sometimes set to the YOLO raw id). Having both lets
    # us migrate the dedup key gradually without breaking legacy writers.
    person_track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Acknowledgement (T5-05) ----------------------------------------
    # NULL = unacknowledged. Set by the Telegram inline-button callback
    # (or a future web-UI button). Dashboard "open alerts" queries filter
    # on IS NULL — a partial index in migration 20260424_03 makes that fast.
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Loose TEXT because we want the audit trail to survive even after
    # the subscriber row gets removed from store_telegram_subscribers.
    acknowledged_by_chat_id: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(back_populates="alerts")
    store: Mapped[Optional["Store"]] = relationship(back_populates="alerts")
    camera: Mapped[Optional["Camera"]] = relationship(back_populates="alerts")
    feedback: Mapped[Optional["AlertFeedback"]] = relationship(back_populates="alert", uselist=False)

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, person_id={self.person_id}, score={self.confidence_score})>"
