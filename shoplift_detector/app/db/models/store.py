from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .alert import Alert
    from .camera import Camera
    from .organization import Organization


class Store(Base, TimestampMixin):
    """Дэлгүүр/салбар - байгууллага бүр олон дэлгүүртэй байж болно."""
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # AI тохиргоо - дэлгүүр бүрт тохируулах боломжтой
    alert_threshold: Mapped[float] = mapped_column(Float, default=80.0)
    alert_cooldown: Mapped[int] = mapped_column(Integer, default=15)

    # Telegram мэдэгдэл - дэлгүүр бүрт өөр chat_id байж болно
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Unified AI/notification settings (JSONB). See
    # app/schemas/store_settings.py for the authoritative shape. Nullable
    # until the follow-up migration enforces NOT NULL after dual-write.
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="stores")
    cameras: Mapped[list["Camera"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="store")

    def __repr__(self) -> str:
        return f"<Store(id={self.id}, name='{self.name}', org_id={self.organization_id})>"
