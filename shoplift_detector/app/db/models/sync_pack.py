from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

SYNC_PACK_STATUSES = (
    "pending",
    "downloaded",
    "applied",
    "failed",
    "rolled_back",
)


class SyncPack(Base, TimestampMixin):
    """Tracks weight/case sync packs published per store.

    - Own UUID id
    - integer `store_id` FK
    - `version` follows semver; (store_id, version) is unique so a pack is
      never re-published under the same version label.
    """

    __tablename__ = "sync_packs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'downloaded', 'applied', 'failed', 'rolled_back')",
            name="ck_sync_packs_status",
        ),
        UniqueConstraint("store_id", "version", name="uq_sync_packs_store_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[str] = mapped_column(String(32), nullable=False)

    weights_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qdrant_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    case_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    s3_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )

    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<SyncPack(id={self.id}, store_id={self.store_id}, "
            f"version='{self.version}', status='{self.status}')>"
        )
