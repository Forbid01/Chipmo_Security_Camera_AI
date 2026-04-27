from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Canonical action identifiers. The DB does not enforce these (the action
# column is free-form VARCHAR) so new events can be added without a
# schema change, but passing through these constants keeps spelling
# consistent across the codebase.
AUDIT_ACTIONS = {
    "view_clip": "view_clip",
    "download_clip": "download_clip",
    "share_clip": "share_clip",
    "label_clip": "label_clip",
    "delete_clip": "delete_clip",
    "view_alert": "view_alert",
    "export_alerts": "export_alerts",
    "config_change": "config_change",
    "user_created": "user_created",
    "user_deleted": "user_deleted",
    "store_settings_change": "store_settings_change",
    "sync_pack_apply": "sync_pack_apply",
    "installer_download_issued": "installer_download_issued",
}


class AuditLog(Base):
    """Compliance audit trail.

    Polymorphic resource reference per schema lock §7.5:
    - `resource_type` names the entity kind (e.g. 'clip', 'alert',
      'store', 'user')
    - `resource_int_id` carries integer FKs for current core tables
    - `resource_uuid` carries UUIDs for new-schema tables (cases,
      sync_packs)
    - `resource_key` is an opaque string for non-database resources
      (e.g. S3 paths, config keys)

    Use at most one of the three resource columns per row.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(String(64), nullable=False)

    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_int_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resource_uuid: Mapped[UUID | None] = mapped_column(nullable=True)
    resource_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, user_id={self.user_id}, "
            f"action='{self.action}', resource_type={self.resource_type})>"
        )
