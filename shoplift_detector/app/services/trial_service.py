"""14-day trial activation (T2-07).

Flow: email-verified tenant picks a plan on /plan, clicks "Start
14-day trial" → this service:

1. Confirms the tenant is in (status=pending, onboarding_step=pending_plan).
2. Atomically transitions status → active, sets trial_ends_at = now + 14d,
   installs the "trial" resource_quota (Pro features, 5-cam cap), and
   advances onboarding_step → pending_payment.
3. Generates a fresh API key and overwrites the signup-time hash so
   the raw token can be returned exactly once.
4. Audits the state change.

The pre-activation api_key_hash is effectively throwaway — signup never
surfaced it. Overwriting is therefore safe and saves us from running
the rotation overlap window at this boundary (the customer has no
deployed agents yet).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.db.models.audit_log import AUDIT_ACTIONS
from app.db.repository.audit_log import AuditLogRepository
from app.db.repository.tenants import TenantRepository
from app.services.api_key_service import IssuedApiKey, generate_api_key
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TRIAL_DURATION = timedelta(days=14)

# "Full Pro features with a 5-camera cap" per T2-07 DoD. Every
# non-camera dimension matches Pro so a trialling customer can
# exercise cross-camera Re-ID, multi-channel alerts, and full GPU
# time for the 14-day window.
TRIAL_ACTIVE_QUOTA: dict[str, int | None] = {
    "max_cameras": 5,
    "max_stores": 1,
    "max_gpu_seconds_per_day": 86_400,
    "max_storage_gb": 100,
    "max_api_calls_per_minute": 60,
}

TRIAL_ACTIVATED_ACTION = "trial_activated"
AUDIT_ACTIONS.setdefault(TRIAL_ACTIVATED_ACTION, TRIAL_ACTIVATED_ACTION)


class TrialActivationError(ValueError):
    """Base class for activation refusals — handler maps to 400."""


class TrialAlreadyActive(TrialActivationError):
    """Tenant has already moved past pending_plan."""


class TrialNotEligible(TrialActivationError):
    """Status / onboarding combination isn't a valid activation point."""


@dataclass(frozen=True)
class TrialActivationResult:
    tenant_id: UUID
    raw_api_key: str
    trial_ends_at: datetime
    plan: str
    onboarding_step: str
    resource_quota: dict[str, Any]


async def activate_trial(
    db: AsyncSession,
    *,
    email: str,
    now: datetime | None = None,
) -> TrialActivationResult:
    """Promote a pending tenant to active trial.

    Raises:
        TrialNotEligible — tenant not found, status != pending, or
            onboarding_step != pending_plan.
        TrialAlreadyActive — onboarding has already advanced past
            pending_plan (idempotent replays would change state in
            surprising ways).
    """
    import json

    now = now or datetime.now(UTC)
    tenant_repo = TenantRepository(db)

    tenant = await tenant_repo.get_by_email(email)
    if tenant is None:
        raise TrialNotEligible("tenant not found")

    step = tenant.get("onboarding_step")
    status = tenant.get("status")

    if step in ("pending_payment", "completed"):
        raise TrialAlreadyActive(
            f"trial already activated (step={step!r})"
        )
    if step != "pending_plan" or status != "pending":
        raise TrialNotEligible(
            f"activation blocked (status={status!r}, step={step!r})"
        )

    issued = generate_api_key()
    trial_ends = now + TRIAL_DURATION

    # Atomic update. WHERE guards on the pre-activation state so a
    # second concurrent request fails the rowcount check and returns
    # `TrialAlreadyActive` without corrupting the tenant row.
    update = text("""
        UPDATE tenants
           SET status = 'active',
               plan = 'trial',
               trial_ends_at = :trial_ends,
               onboarding_step = 'pending_payment',
               resource_quota = CAST(:resource_quota AS JSONB),
               api_key_hash = :new_hash,
               status_changed_at = :now
         WHERE tenant_id = CAST(:tenant_id AS UUID)
           AND status = 'pending'
           AND onboarding_step = 'pending_plan'
    """)
    result = await db.execute(
        update,
        {
            "tenant_id": str(tenant["tenant_id"]),
            "trial_ends": trial_ends,
            "resource_quota": json.dumps(TRIAL_ACTIVE_QUOTA),
            "new_hash": issued.hashed,
            "now": now,
        },
    )
    if result.rowcount == 0:
        # Another request beat us to it — re-raise as the idempotent
        # "already active" error so the handler can 409/400 cleanly.
        raise TrialAlreadyActive("activation lost to concurrent update")

    audit_repo = AuditLogRepository(db)
    await audit_repo.log(
        action=TRIAL_ACTIVATED_ACTION,
        user_id=None,
        resource_type="tenant",
        resource_uuid=tenant["tenant_id"],
        details={
            "trial_ends_at": trial_ends.isoformat(),
            "quota": TRIAL_ACTIVE_QUOTA,
        },
    )
    await db.commit()

    logger.info(
        "trial_activated",
        extra={
            "tenant_id": str(tenant["tenant_id"]),
            "trial_ends_at": trial_ends.isoformat(),
        },
    )

    return TrialActivationResult(
        tenant_id=tenant["tenant_id"],
        raw_api_key=issued.raw,
        trial_ends_at=trial_ends,
        plan="trial",
        onboarding_step="pending_payment",
        resource_quota=dict(TRIAL_ACTIVE_QUOTA),
    )


__all__ = [
    "TRIAL_ACTIVE_QUOTA",
    "TRIAL_DURATION",
    "TRIAL_ACTIVATED_ACTION",
    "TrialActivationError",
    "TrialAlreadyActive",
    "TrialNotEligible",
    "TrialActivationResult",
    "activate_trial",
]


# Keep the IssuedApiKey import reachable for tests that assert
# rotation vs. fresh-overwrite behavior via introspection.
_KEY = IssuedApiKey
