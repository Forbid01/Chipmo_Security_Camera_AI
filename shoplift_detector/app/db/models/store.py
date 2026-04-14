from sqlalchemy import String, Integer, ForeignKey, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional
from .base import Base, TimestampMixin


class Store(Base, TimestampMixin):
    """Дэлгүүр/салбар - байгууллага бүр олон дэлгүүртэй байж болно."""
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # AI тохиргоо - дэлгүүр бүрт тохируулах боломжтой
    alert_threshold: Mapped[float] = mapped_column(Float, default=80.0)
    alert_cooldown: Mapped[int] = mapped_column(Integer, default=15)

    # Telegram мэдэгдэл - дэлгүүр бүрт өөр chat_id байж болно
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="stores")
    cameras: Mapped[List["Camera"]] = relationship(back_populates="store", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="store")

    def __repr__(self) -> str:
        return f"<Store(id={self.id}, name='{self.name}', org_id={self.organization_id})>"
