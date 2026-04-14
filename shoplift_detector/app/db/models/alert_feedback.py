from sqlalchemy import String, Integer, ForeignKey, Text, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func
from typing import Optional
from datetime import datetime
from .base import Base


class AlertFeedback(Base):
    """Ажилтнуудын alert-д өгсөн feedback - auto-learning-д ашиглана."""
    __tablename__ = "alert_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    store_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feedback_type: Mapped[str] = mapped_column(
        String(20), nullable=False  # true_positive, false_positive
    )
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Behavior scores at time of alert (for learning)
    score_at_alert: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    behaviors_detected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    alert: Mapped["Alert"] = relationship(back_populates="feedback")

    def __repr__(self) -> str:
        return f"<AlertFeedback(id={self.id}, alert_id={self.alert_id}, type='{self.feedback_type}')>"
