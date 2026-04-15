from app.core.security import AdminOrAbove, SuperAdmin
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
    repo = CameraRepository(db)
    if store_id:
        cameras = await repo.get_by_store(store_id)
    elif organization_id:
        cameras = await repo.get_by_organization(organization_id)
    else:
        cameras = await repo.get_all()
    return cameras


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
async def camera_status(admin: AdminOrAbove):
    from app.services.camera_manager import camera_manager
    return camera_manager.get_all_status()
