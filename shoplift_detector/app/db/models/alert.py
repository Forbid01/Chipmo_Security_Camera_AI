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

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(back_populates="alerts")
    store: Mapped[Optional["Store"]] = relationship(back_populates="alerts")
    camera: Mapped[Optional["Camera"]] = relationship(back_populates="alerts")
    feedback: Mapped[Optional["AlertFeedback"]] = relationship(back_populates="alert", uselist=False)

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, person_id={self.person_id}, score={self.confidence_score})>"
