from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Lifecycle states enumerated by the roadmap (06 §8.2).
TENANT_STATUSES = ("pending", "active", "suspended", "grace", "churned")

# Plans enumerated by 03_Sentry_Pricing_Business_Model.md §2.
TENANT_PLANS = ("trial", "starter", "pro", "enterprise")

# Onboarding wizard sub-states (orthogonal to lifecycle `status`).
# pending_email → pending_plan → pending_payment → completed.
ONBOARDING_STEPS = (
    "pending_email",
    "pending_plan",
    "pending_payment",
    "completed",
)


class Tenant(Base):
    """Canonical tenant identity row per Sentry DOC-05 §2.1.

    One row per paying (or trialing) customer. Owns the plan, status,
    resource quotas, and hashed API key that every API request resolves
    through `get_current_tenant`. `tenant_id` is the UUID that every
    tenant-scoped table FKs.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'grace', 'churned')",
            name="ck_tenants_status",
        ),
        CheckConstraint(
            "plan IN ('trial', 'starter', 'pro', 'enterprise')",
            name="ck_tenants_plan",
        ),
        CheckConstraint(
            "onboarding_step IN ("
            "'pending_email', 'pending_plan', "
            "'pending_payment', 'completed')",
            name="ck_tenants_onboarding_step",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    plan: Mapped[str] = mapped_column(
        Text, nullable=False, default="trial", server_default="trial"
    )
    onboarding_step: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_email",
        server_default="pending_email",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Updated every time `status` changes (T1-10). Purge cron uses it
    # to decide which churned tenants have passed the 90-day grace.
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Stripe customer / QPay payer token. Raw PAN never touches this column.
    payment_method_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SHA-256 hex of the raw `sk_live_*` API key. Raw key is shown to the
    # operator exactly once at generation time and never persisted.
    api_key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )

    # 24-hour rotation overlap (T1-06). After rotation, the old hash
    # lives here until `previous_api_key_expires_at` passes, then the
    # sweeper cron clears both.
    previous_api_key_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    previous_api_key_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    resource_quota: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Tenant(tenant_id={self.tenant_id}, "
            f"display_name={self.display_name!r}, "
            f"plan={self.plan!r}, status={self.status!r})>"
        )
