from app.core.security import AdminOrAbove, CurrentUser, SuperAdmin
from app.core.tenant_auth import CurrentTenant
from app.db.repository.camera_repo import CameraRepository
from app.db.session import DB
from app.schemas.camera import (
    CameraCreate,
    CameraTestRequest,
    CameraTestResponse,
    CameraUpdate,
    ShelfZonesUpdate,
)
from app.schemas.common import APIResponse
from app.services.camera_test import test_camera as run_camera_test
from app.services.onboarding_events import CAMERA_TESTED, broker, make_event
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post(
    "/test",
    response_model=CameraTestResponse,
    summary="Probe an RTSP URL — decode 1 frame + FPS estimate (T4-11).",
)
async def test_camera_connection(
    payload: CameraTestRequest,
    tenant: CurrentTenant,
) -> CameraTestResponse:
    """Connect to the supplied RTSP URL, grab a single frame, and
    return a JPEG-encoded thumbnail plus an FPS estimate measured from
    a short sample window. On failure surface vendor-specific
    credential hints (T4-14) so the customer can adjust in-place.

    The endpoint is tenant-authenticated but does not persist
    anything — test payloads are transient.
    """
    result = run_camera_test(
        str(payload.url),
        manufacturer_id=payload.manufacturer_id,
    )

    # Publish to the onboarding stream so /connect-cameras (T4-13)
    # highlights the newly-tested camera row in real time. Raw URL
    # is NOT included — it carries credentials.
    await broker.publish(
        str(tenant["tenant_id"]),
        make_event(
            CAMERA_TESTED,
            payload={
                "ok": result.ok,
                "fps": result.fps,
                "manufacturer_id": payload.manufacturer_id,
            },
        ),
    )

    return CameraTestResponse(**result.to_dict())


@router.get("")
async def list_cameras(
    admin: AdminOrAbove,
    db: DB,
    store_id: int | None = None,
    organization_id: int | None = None,
):
    """Camera listing. Closes H-H3 from T02-12 by scoping the fallback
    to the caller's organization instead of returning every tenant's
    cameras to a non-super admin.
    """
    repo = CameraRepository(db)

    if admin.get("role") == "super_admin":
        if store_id:
            return await repo.get_by_store(store_id)
        if organization_id:
            return await repo.get_by_organization(organization_id)
        return await repo.get_all()

    # Non-super admin: never fall through to get_all(). If the caller
    # asked for another org's data, return empty rather than leaking.
    admin_org = admin.get("org_id")
    if organization_id and organization_id != admin_org:
        return []
    if store_id:
        return [c for c in await repo.get_by_store(store_id)
                if c.get("organization_id") == admin_org]
    return await repo.get_by_organization(admin_org) if admin_org else []


@router.post("", response_model=APIResponse)
async def create_camera(data: CameraCreate, admin: SuperAdmin, db: DB):
    repo = CameraRepository(db)
    cam_id = await repo.create(data)

    # Register with camera manager for live streaming
    from app.services.camera_manager import camera_manager
    camera_manager.register_camera(
        camera_id=cam_id,
        store_id=data.store_id,
        name=data.name,
        url=data.url,
        camera_type=data.camera_type,
        is_ai_enabled=data.is_ai_enabled,
    )

    return APIResponse(message="Камер нэмэгдлээ", data={"camera_id": cam_id})


@router.put("/{camera_id}", response_model=APIResponse)
async def update_camera(camera_id: int, data: CameraUpdate, admin: SuperAdmin, db: DB):
    repo = CameraRepository(db)
    success = await repo.update(camera_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")

    # Re-register camera if URL or settings changed
    if data.url or data.is_active is not None:
        from app.services.camera_manager import camera_manager
        camera_manager.unregister_camera(camera_id)
        if data.is_active is not False:
            cam = await repo.get_all()
            for c in cam:
                if c["id"] == camera_id:
                    camera_manager.register_camera(
                        camera_id=camera_id,
                        store_id=c.get("store_id", 0),
                        name=c["name"],
                        url=c["url"],
                        camera_type=c.get("camera_type", "rtsp"),
                        is_ai_enabled=c.get("is_ai_enabled", True),
                        shelf_zones=c.get("shelf_zones") or [],
                    )
                    break

    return APIResponse(message="Камер шинэчлэгдлээ")


@router.delete("/{camera_id}", response_model=APIResponse)
async def delete_camera(camera_id: int, admin: SuperAdmin, db: DB):
    from app.services.camera_manager import camera_manager
    camera_manager.unregister_camera(camera_id)

    repo = CameraRepository(db)
    success = await repo.delete(camera_id)
    if not success:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")
    return APIResponse(message="Камер устгагдлаа")


@router.get("/status")
async def camera_status(user: CurrentUser, db: DB):
    """Return camera status keyed by camera_id so the UI can O(1) lookup.

    Tenant-scoped (H-H6 remediation): non-super users only see statuses
    for cameras in their organization. The camera_manager itself holds
    runtime state for every camera, so we filter via the DB camera
    list before returning.
    """
    from app.services.camera_manager import camera_manager

    statuses = camera_manager.get_all_status()

    if user.get("role") == "super_admin":
        visible_ids: set[int] | None = None  # None = show all
    else:
        user_org = user.get("org_id")
        if not user_org:
            return {}
        repo = CameraRepository(db)
        org_cameras = await repo.get_by_organization(user_org)
        visible_ids = {c["id"] for c in org_cameras}

    result = {}
    for s in statuses:
        cam_id = s.get("camera_id")
        if visible_ids is not None and cam_id not in visible_ids:
            continue
        result[str(cam_id)] = {**s, "online": bool(s.get("is_connected"))}
    return result


@router.get("/{camera_id}/shelf-zones")
async def get_camera_shelf_zones(camera_id: int, user: CurrentUser, db: DB):
    """Return the shelf ROI polygons configured for a camera.

    Tenant-scoped: non-super users can only see zones for cameras in their
    own organization.
    """
    repo = CameraRepository(db)

    org_id = None
    if user.get("role") != "super_admin":
        org_id = user.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="No organization")

    return {"zones": await repo.get_shelf_zones(camera_id, organization_id=org_id)}


@router.put("/{camera_id}/shelf-zones", response_model=APIResponse)
async def update_camera_shelf_zones(
    camera_id: int,
    data: ShelfZonesUpdate,
    admin: AdminOrAbove,
    db: DB,
):
    """Replace the shelf ROI polygons for a camera.

    Also pushes the new zones into the in-memory CameraState so the AI
    pipeline starts using them on the next frame without a restart.
    """
    repo = CameraRepository(db)

    org_id = None if admin.get("role") == "super_admin" else admin.get("org_id")
    zones_payload = [z.model_dump() for z in data.zones]

    success = await repo.update_shelf_zones(
        camera_id,
        zones_payload,
        organization_id=org_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй")

    from app.services.camera_manager import camera_manager
    camera_manager.update_shelf_zones(camera_id, zones_payload)

    return APIResponse(
        message="Shelf zones шинэчлэгдлээ",
        data={"camera_id": camera_id, "count": len(zones_payload)},
    )
