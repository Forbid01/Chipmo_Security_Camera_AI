from sqlalchemy import String, Integer, ForeignKey, Boolean, Text, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func
from typing import Optional
from datetime import datetime
from .base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    store_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
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
