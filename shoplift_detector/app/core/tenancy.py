"""Tenant-scoped access dependencies.

Implements the Layer-1 enforcement path from T02-13. For every resource
type the audit (T02-12) flagged as cross-tenant reachable, this module
exposes a FastAPI dependency factory that:

1. Resolves the resource through its repository.
2. Confirms the authenticated user's organization owns the resource.
3. Raises **404** (not 403) for cross-tenant access — so enumerating
   ids from another tenant can't leak existence. 403 is reserved for
   "right tenant, wrong role".
4. Returns the resolved resource dict so the handler does not fetch
   twice.

SuperAdmin short-circuits every check — they see everything.

Usage:

    from app.core.tenancy import require_alert_access

    @router.delete("/alerts/{alert_id}")
    async def delete_alert(
        alert_id: int,
        alert: Annotated[dict, Depends(require_alert_access)],
        db: DB,
    ):
        # `alert` is already confirmed to belong to user.org_id
        ...
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.security import CurrentUser
from app.db.session import DB
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _is_super_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "super_admin"


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} олдсонгүй",
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

async def require_store_access(
    store_id: int,
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    from app.db.repository.stores import StoreRepository

    store = await StoreRepository(db).get_by_id(store_id)
    if not store:
        raise _not_found("Дэлгүүр")

    if _is_super_admin(user):
        return store

    user_org = user.get("org_id")
    if user_org is None or store.get("organization_id") != user_org:
        # 404, not 403 — don't leak existence of another tenant's store.
        raise _not_found("Дэлгүүр")

    return store


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

async def require_camera_access(
    camera_id: int,
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    from sqlalchemy import text

    # Direct SELECT is cheaper than iterating CameraRepository.get_all()
    # which is what the legacy handlers were doing per the T02-12 audit.
    query = text("""
        SELECT id, name, url, camera_type, store_id, organization_id,
               is_active, is_ai_enabled
        FROM cameras
        WHERE id = :id
        LIMIT 1
    """)
    result = await db.execute(query, {"id": camera_id})
    row = result.mappings().fetchone()
    if not row:
        raise _not_found("Камер")

    camera = dict(row)
    if _is_super_admin(user):
        return camera

    user_org = user.get("org_id")
    if user_org is None or camera.get("organization_id") != user_org:
        raise _not_found("Камер")

    return camera


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

async def require_alert_access(
    alert_id: int,
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    from sqlalchemy import text

    # Alert's own `organization_id` column isn't reliably populated on
    # legacy rows; derive through cameras when present. This matches
    # the existing pattern in AlertRepository._build_alert_query_parts.
    query = text("""
        SELECT a.id,
               a.person_id,
               a.organization_id,
               a.store_id,
               a.camera_id,
               a.event_time,
               a.image_path,
               a.description,
               COALESCE(a.organization_id, c.organization_id) AS effective_org_id
        FROM alerts a
        LEFT JOIN cameras c ON a.camera_id = c.id
        WHERE a.id = :id
        LIMIT 1
    """)
    result = await db.execute(query, {"id": alert_id})
    row = result.mappings().fetchone()
    if not row:
        raise _not_found("Alert")

    alert = dict(row)
    if _is_super_admin(user):
        return alert

    user_org = user.get("org_id")
    if user_org is None or alert.get("effective_org_id") != user_org:
        raise _not_found("Alert")

    return alert


# ---------------------------------------------------------------------------
# Case (T02-03 metadata)
# ---------------------------------------------------------------------------

async def require_case_access(
    case_id: str,
    user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    from sqlalchemy import text

    query = text("""
        SELECT c.*,
               s.organization_id AS effective_org_id
        FROM cases c
        LEFT JOIN stores s ON c.store_id = s.id
        WHERE c.id = CAST(:id AS UUID)
        LIMIT 1
    """)
    result = await db.execute(query, {"id": case_id})
    row = result.mappings().fetchone()
    if not row:
        raise _not_found("Case")

    case = dict(row)
    if _is_super_admin(user):
        return case

    user_org = user.get("org_id")
    if user_org is None or case.get("effective_org_id") != user_org:
        raise _not_found("Case")

    return case
