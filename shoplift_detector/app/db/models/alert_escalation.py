"""Per-channel delivery log for an alert (T5-09)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AlertEscalation(Base):
    __tablename__ = "alert_escalations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Soft FK — no DB constraint so the escalation audit trail
    # survives T2-23's retention sweep of the `alerts` table.
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        outcome = (
            "delivered" if self.delivered_at
            else "failed" if self.failed_at
            else "pending"
        )
        return (
            f"<AlertEscalation(id={self.id}, alert_id={self.alert_id}, "
            f"channel={self.channel!r}, {outcome})>"
        )
