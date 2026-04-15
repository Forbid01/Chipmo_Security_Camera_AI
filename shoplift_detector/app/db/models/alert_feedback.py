from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .alert import Alert


class AlertFeedback(Base):
    """Ажилтнуудын alert-д өгсөн feedback - auto-learning-д ашиглана."""
    __tablename__ = "alert_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feedback_type: Mapped[str] = mapped_column(
        String(20), nullable=False  # true_positive, false_positive
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Behavior scores at time of alert (for learning)
    score_at_alert: Mapped[float | None] = mapped_column(Float, nullable=True)
    behaviors_detected: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    alert: Mapped["Alert"] = relationship(back_populates="feedback")

    def __repr__(self) -> str:
        return f"<AlertFeedback(id={self.id}, alert_id={self.alert_id}, type='{self.feedback_type}')>"
