from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrganizationTenantMap(Base):
    """Bridge row linking a legacy `organizations.id` to its UUID tenant.

    Populated for every existing organization by the T1-02 backfill.
    New signups create the tenant first and insert the map row only
    when a legacy org shell is created for compatibility.
    """

    __tablename__ = "organization_tenant_map"

    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationTenantMap(organization_id={self.organization_id}, "
            f"tenant_id={self.tenant_id})>"
        )
