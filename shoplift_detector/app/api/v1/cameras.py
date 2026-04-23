from app.core.security import AdminOrAbove, CurrentUser, SuperAdmin
from app.db.repository.camera_repo import CameraRepository
from app.db.session import DB
from app.schemas.camera import CameraCreate, CameraUpdate
from app.schemas.common import APIResponse
from fastapi import APIRouter, HTTPException

router = APIRouter()


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
