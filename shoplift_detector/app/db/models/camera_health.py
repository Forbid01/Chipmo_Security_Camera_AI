from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CameraHealth(Base, TimestampMixin):
    __tablename__ = "camera_health"
    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'offline', 'degraded')",
            name="ck_camera_health_status",
        ),
    )

    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        primary_key=True,
    )
    store_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="offline", nullable=False, index=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fps: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    offline_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<CameraHealth(camera_id={self.camera_id}, status='{self.status}')>"
