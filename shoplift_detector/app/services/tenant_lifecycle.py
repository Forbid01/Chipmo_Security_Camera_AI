"""Tenant lifecycle state machine (T1-10, DOC-05 §7.1).

States are defined on the `tenants.status` column by the T1-01
CHECK constraint:

    pending → active → suspended → grace → churned

Valid transitions (canonical graph):

    pending    → active
    active     → suspended        (billing fail, policy violation)
    active     → grace            (customer-initiated cancel)
    suspended  → active           (payment recovered)
    suspended  → grace             (cancellation during suspension)
    suspended  → churned          (admin write-off)
    grace      → active           (customer reactivates before 90d)
    grace      → churned          (90d elapsed; purge cron drives this)

Anything not in the table raises `InvalidTransitionError` → 409. Every
accepted transition appends one row to `audit_log` with the old/new
status so compliance can reconstruct the sequence.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.models.audit_log import AUDIT_ACTIONS
from app.db.models.tenant import TENANT_STATUSES
from app.db.repository.audit_log import AuditLogRepository
from app.db.repository.tenants import TenantRepository
from fastapi import HTTPException, status as http_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Directed adjacency: each key is the current status, the value is the
# set of legal successor statuses.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"active", "churned"}),
    "active": frozenset({"suspended", "grace"}),
    "suspended": frozenset({"active", "grace", "churned"}),
    "grace": frozenset({"active", "churned"}),
    "churned": frozenset(),  # terminal — data purge runs on this edge
}

# Register the transition action on the audit log action catalog so
# `AuditLogRepository.log` round-trips through the same enum surface
# as other actions.
TENANT_STATUS_CHANGE_ACTION = "tenant_status_change"
AUDIT_ACTIONS.setdefault(TENANT_STATUS_CHANGE_ACTION, TENANT_STATUS_CHANGE_ACTION)


class InvalidTransitionError(HTTPException):
    """409 — the requested transition is not in the VALID_TRANSITIONS
    graph. Separate from 404 (tenant missing) or 403 (wrong caller)."""

    def __init__(self, *, current: str, requested: str):
        super().__init__(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "error": "invalid_status_transition",
                "current_status": current,
                "requested_status": requested,
                "allowed_next": sorted(VALID_TRANSITIONS.get(current, set())),
            },
        )


def is_valid_transition(current: str, requested: str) -> bool:
    """Pure predicate — convenient for UI disable-button logic."""
    if current == requested:
        # Idempotent re-apply is not a transition; reject so auditors
        # don't see no-op churn in the log.
        return False
    return requested in VALID_TRANSITIONS.get(current, frozenset())


async def transition_tenant_status(
    db: AsyncSession,
    *,
    tenant_id: UUID | str,
    new_status: str,
    actor_user_id: int | None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Atomically flip a tenant's status after validating the edge.

    Writes an audit_log row in the same transaction so a crash can't
    leave the status and the log out of sync.

    Raises:
        404 — tenant not found
        400 — `new_status` is not a known state
        409 — transition is not in the VALID_TRANSITIONS graph
    """
    if new_status not in TENANT_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown status {new_status!r}. "
                f"Allowed: {', '.join(TENANT_STATUSES)}"
            ),
        )

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Tenant олдсонгүй",
        )

    current = tenant.get("status") or "pending"
    if not is_valid_transition(current, new_status):
        raise InvalidTransitionError(current=current, requested=new_status)

    update_query = text("""
        UPDATE tenants
           SET status = :new_status,
               status_changed_at = now()
         WHERE tenant_id = CAST(:tenant_id AS UUID)
    """)
    await db.execute(
        update_query,
        {"tenant_id": str(tenant_id), "new_status": new_status},
    )

    audit_repo = AuditLogRepository(db)
    await audit_repo.log(
        action=TENANT_STATUS_CHANGE_ACTION,
        user_id=actor_user_id,
        resource_type="tenant",
        resource_uuid=tenant_id,
        details={
            "from": current,
            "to": new_status,
            "reason": reason,
        },
    )
    await db.commit()

    logger.info(
        "tenant_status_changed",
        extra={
            "tenant_id": str(tenant_id),
            "from": current,
            "to": new_status,
            "actor_user_id": actor_user_id,
        },
    )

    return {"tenant_id": str(tenant_id), "from": current, "to": new_status}
