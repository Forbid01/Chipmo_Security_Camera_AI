"""Customer-portal viewer for per-channel escalation history (T5-09).

Read-only. Scoped to the authenticated user's organization — you can
only see escalations for alerts that belong to your org. Cross-tenant
access returns 404 (not 403) to match the enumeration-safe pattern
used across the rest of `/api/v1`.
"""

from __future__ import annotations

from app.core.security import CurrentUser
from app.db.repository.alert_escalations import AlertEscalationRepository
from app.db.repository.alerts import AlertRepository
from app.db.session import DB
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/{alert_id}/escalations")
async def list_alert_escalations(
    alert_id: int,
    user: CurrentUser,
    db: DB,
):
    """Return every delivery attempt for a given alert, newest first."""
    alerts_repo = AlertRepository(db)
    alert = await alerts_repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    role = user.get("role")
    if role != "super_admin":
        # Scope to the caller's org — anything else is 404 (not 403)
        # so attackers can't enumerate alert_ids across tenants.
        if alert.get("organization_id") != user.get("org_id"):
            raise HTTPException(status_code=404, detail="Alert not found")

    rows = await AlertEscalationRepository(db).list_for_alert(alert_id)
    return {"alert_id": alert_id, "escalations": rows}
