from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AlertStateRecord(Base, TimestampMixin):
    __tablename__ = "alert_state"
    __table_args__ = (
        UniqueConstraint("camera_id", "person_track_id", name="uq_alert_state_camera_person"),
        CheckConstraint(
            "state IN ('idle', 'active', 'cooldown', 'resolved')",
            name="ck_alert_state_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    person_track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    last_alert_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            "<AlertStateRecord("
            f"camera_id={self.camera_id}, "
            f"person_track_id={self.person_track_id}, "
            f"state='{self.state}'"
            ")>"
        )
