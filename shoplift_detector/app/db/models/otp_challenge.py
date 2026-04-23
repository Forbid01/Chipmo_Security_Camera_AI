from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

OTP_CHANNELS = ("email", "sms")


class OtpChallenge(Base):
    """Single-use OTP code issued during signup / verification.

    One row per (tenant, channel, send). Verify flow increments
    `attempts`; at `max_attempts` the row is treated as used. `used_at`
    is stamped on successful verification so the code cannot be
    replayed.
    """

    __tablename__ = "otp_challenges"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'sms')",
            name="ck_otp_challenges_channel",
        ),
        CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts",
            name="ck_otp_challenges_attempts",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<OtpChallenge(id={self.id}, tenant_id={self.tenant_id}, "
            f"channel={self.channel!r}, used={bool(self.used_at)})>"
        )
