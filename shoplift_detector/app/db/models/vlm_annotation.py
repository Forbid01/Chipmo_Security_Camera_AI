from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .alert import Alert


class VlmAnnotation(Base):
    """Qwen2.5-VL output cached against a specific alert.

    The VLM call is async + slow (1-5s on GPU); we persist the result so
    the frontend can render it asynchronously and the auto-learner can
    train on operator-confirmed VLM verdicts later.
    """

    __tablename__ = "vlm_annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Mapped[Optional["Alert"]] = relationship()

    def __repr__(self) -> str:
        return (
            f"<VlmAnnotation(alert_id={self.alert_id}, "
            f"conf={self.confidence})>"
        )
