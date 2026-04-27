"""Store-level Telegram subscriber (T5-04).

Many-to-one mapping on top of `stores`: one row per (store, chat).
`role` gates future per-severity routing (e.g. owners get RED,
managers get ORANGE+).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .store import Store


class StoreTelegramSubscriber(Base):
    __tablename__ = "store_telegram_subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="manager")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    store: Mapped["Store"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<StoreTelegramSubscriber(id={self.id}, store_id={self.store_id}, "
            f"chat_id={self.chat_id!r}, role={self.role!r})>"
        )
