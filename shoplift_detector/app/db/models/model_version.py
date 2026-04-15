from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ModelVersion(Base):
    """AI моделийн хувилбар бүртгэл - auto-learning хувилбарын түүх."""
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pose, detection
    weights_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Performance metrics
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_feedback_used: Mapped[int] = mapped_column(Integer, default=0)

    # Threshold adjustments learned from feedback
    learned_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    learned_score_weights: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ModelVersion(id={self.id}, store_id={self.store_id}, v='{self.version}')>"
