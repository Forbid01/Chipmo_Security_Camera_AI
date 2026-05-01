from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated

from app.core.alert_broadcaster import alert_broadcaster
from app.core.config import ALERTS_DIR
from app.core.security import BearerToken, CurrentUser, SuperAdmin, _decode_token, _extract_token
from app.core.tenancy import require_alert_access
from app.db.models.vlm_annotation import VlmAnnotation
from app.db.repository.alerts import AlertRepository
from app.db.repository.stores import StoreRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

router = APIRouter()


@router.get("")
async def get_alerts(
    request: Request,
    user: CurrentUser,
    db: DB,
    limit: int = 20,
    offset: int = 0,
    store_id: int | None = None,
):
    repo = AlertRepository(db)
    org_id = user.get("org_id")

    if user.get("role") == "super_admin":
        alerts = await repo.get_latest_alerts(
            organization_id=None, store_id=store_id, limit=limit, offset=offset
        )
    else:
        alerts = await repo.get_latest_alerts(
            organization_id=org_id, store_id=store_id, limit=limit, offset=offset
        )

    base_url = str(request.base_url).rstrip("/")
    for alert in alerts:
        image_path = alert.get("image_path")
        if not image_path:
            alert["web_url"] = None
            alert["video_url"] = None
            continue

        file_name = os.path.basename(image_path)
        video_name = file_name.replace(".jpg", ".mp4")
        video_full_path = os.path.join(ALERTS_DIR, video_name)
        alert["web_url"] = f"{base_url}/static/{file_name}"
        alert["video_url"] = (
            f"{base_url}/static/{video_name}" if os.path.exists(video_full_path) else None
        )

    return {"status": "success", "data": alerts}


@router.get("/stream")
async def stream_alerts_sse(
    request: Request,
    db: DB,
    token: str | None = None,
    bearer_token: BearerToken = None,
):
    """Server-Sent Events stream for real-time alert delivery.

    Authentication: accepts a JWT via `?token=` query param (required for
    browser EventSource which cannot set custom headers) or the standard
    httpOnly cookie / Authorization header.

    Each connected client receives only alerts that belong to their
    organisation.  Super-admins receive all alerts.
    """
    raw_token = token or _extract_token(request, bearer_token)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Нэвтрэх шаардлагатай")
    try:
        user = _decode_token(raw_token)
    except HTTPException:
        raise

    org_id = user.get("org_id")
    role = user.get("role")

    # Determine which store_ids this user may see (resolved once at connect).
    if role == "super_admin":
        allowed_store_ids = None  # None → all stores
    else:
        store_rows = await StoreRepository(db).get_by_organization(org_id)
        allowed_store_ids: set[int] = {int(s["id"]) for s in store_rows}

    async def event_generator():
        q = await alert_broadcaster.subscribe()
        try:
            # Signal to the client that the stream is open.
            yield "event: connected\ndata: {}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)

                    # Tenant filter: drop events that don't belong to this user.
                    sid = payload.get("store_id")
                    if allowed_store_ids is not None:
                        if sid is None or int(sid) not in allowed_store_ids:
                            continue

                    yield f"event: alert\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment — prevents proxies from closing idle streams.
                    yield ": keepalive\n\n"
        finally:
            await alert_broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/admin")
async def get_admin_alerts(
    admin: SuperAdmin,
    db: DB,
    organization_id: int | None = None,
    store_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    repo = AlertRepository(db)
    return await repo.get_all_alerts_admin(organization_id, store_id, limit, offset)


@router.put("/{alert_id}/reviewed", response_model=APIResponse)
async def mark_reviewed(alert_id: int, admin: SuperAdmin, db: DB):
    repo = AlertRepository(db)
    success = await repo.mark_alert_reviewed(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert олдсонгүй")
    return APIResponse(message="Alert шалгагдсан гэж тэмдэглэгдлээ")


@router.delete("/{alert_id}", response_model=APIResponse)
async def delete_alert(alert_id: int, admin: SuperAdmin, db: DB):
    repo = AlertRepository(db)
    success = await repo.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert олдсонгүй")
    return APIResponse(message="Alert устгагдлаа")


@router.get("/{alert_id}/vlm-annotation")
async def get_vlm_annotation(
    alert_id: int,
    db: DB,
    alert: Annotated[dict, Depends(require_alert_access)],
):
    """Return the VLM caption + reasoning for an alert.

    Tenant-guarded by `require_alert_access`. Returns 404 when no
    annotation row exists yet (the VLM persist is async, so a fresh
    alert may briefly have no row).
    """
    result = await db.execute(
        select(VlmAnnotation).where(VlmAnnotation.alert_id == alert_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="VLM annotation хараахан бэлэн биш")
    return {
        "alert_id": row.alert_id,
        "model_name": row.model_name,
        "caption": row.caption,
        "confidence": row.confidence,
        "reasoning": row.reasoning,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at,
    }
