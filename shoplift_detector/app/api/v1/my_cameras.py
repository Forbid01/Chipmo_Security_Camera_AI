"""Хэрэглэгч өөрийн байгууллагын камеруудыг удирдах endpoint-ууд.
Super admin биш ч камер нэмж, засаж, устгаж чадна - зөвхөн өөрийн org-д."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.db.repository.camera_repo import CameraRepository
from app.db.repository.stores import StoreRepository
from app.schemas.camera import CameraCreate, CameraUpdate
from app.schemas.common import APIResponse

router = APIRouter()


async def _verify_store_ownership(store_id: int, user: dict, db: AsyncSession):
    """Хэрэглэгчийн байгууллагын дэлгүүр эсэхийг шалгах."""
    store_repo = StoreRepository(db)
    store = await store_repo.get_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    if user.get("role") != "super_admin" and store.get("organization_id") != user.get("org_id"):
        raise HTTPException(status_code=403, detail="Энэ дэлгүүрт хандах эрхгүй")
    return store


@router.get("")
async def my_cameras(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хэрэглэгчийн байгууллагын бүх камерууд."""
    repo = CameraRepository(db)
    org_id = user.get("org_id")
    if not org_id and user.get("role") != "super_admin":
        return []
    if user.get("role") == "super_admin":
        return await repo.get_all()
    return await repo.get_by_organization(org_id)


@router.get("/stores")
async def my_stores(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хэрэглэгчийн байгууллагын бүх дэлгүүрүүд."""
    store_repo = StoreRepository(db)
    org_id = user.get("org_id")
    if not org_id and user.get("role") != "super_admin":
        return []
    if user.get("role") == "super_admin":
        return await store_repo.get_all()
    return await store_repo.get_by_organization(org_id)


@router.post("", response_model=APIResponse)
async def add_my_camera(
    data: CameraCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хэрэглэгч өөрийн байгууллагын дэлгүүрт камер нэмэх."""
    await _verify_store_ownership(data.store_id, user, db)

    # org_id-г автоматаар оруулах
    data.organization_id = user.get("org_id")

    repo = CameraRepository(db)
    cam_id = await repo.create(data)

    # CameraManager-д бүртгэх (шууд ажиллаж эхэлнэ)
    from app.services.camera_manager import camera_manager
    camera_manager.register_camera(
        camera_id=cam_id,
        store_id=data.store_id,
        name=data.name,
        url=data.url,
        camera_type=data.camera_type,
        is_ai_enabled=data.is_ai_enabled,
    )

    return APIResponse(message="Камер амжилттай нэмэгдлээ", data={"camera_id": cam_id})


@router.put("/{camera_id}", response_model=APIResponse)
async def update_my_camera(
    camera_id: int,
    data: CameraUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хэрэглэгч өөрийн байгууллагын камер засах."""
    repo = CameraRepository(db)

    # Одоогийн камерын мэдээлэл авах
    all_cams = await repo.get_by_organization(user.get("org_id")) if user.get("role") != "super_admin" else await repo.get_all()
    cam = next((c for c in all_cams if c["id"] == camera_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй эсвэл эрхгүй")

    # Шинэ store_id байвал эрх шалгах
    if data.store_id:
        await _verify_store_ownership(data.store_id, user, db)

    success = await repo.update(camera_id, data)
    if not success:
        raise HTTPException(status_code=400, detail="Шинэчлэх боломжгүй")

    # CameraManager дахин бүртгэх
    from app.services.camera_manager import camera_manager
    camera_manager.unregister_camera(camera_id)

    if data.is_active is not False:
        updated_cams = await repo.get_all()
        for c in updated_cams:
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
async def delete_my_camera(
    camera_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Хэрэглэгч өөрийн байгууллагын камер устгах."""
    repo = CameraRepository(db)

    all_cams = await repo.get_by_organization(user.get("org_id")) if user.get("role") != "super_admin" else await repo.get_all()
    cam = next((c for c in all_cams if c["id"] == camera_id), None)
    if not cam:
        raise HTTPException(status_code=404, detail="Камер олдсонгүй эсвэл эрхгүй")

    from app.services.camera_manager import camera_manager
    camera_manager.unregister_camera(camera_id)

    success = await repo.delete(camera_id)
    if not success:
        raise HTTPException(status_code=400, detail="Устгах боломжгүй")

    return APIResponse(message="Камер устгагдлаа")
