from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_super_admin, require_admin_or_above
from app.db.session import get_db
from app.db.repository.stores import StoreRepository
from app.schemas.store import StoreCreate, StoreUpdate, StoreResponse
from app.schemas.common import APIResponse

router = APIRouter()


@router.get("")
async def list_stores(
    organization_id: int = None,
    admin: dict = Depends(require_admin_or_above),
    db: AsyncSession = Depends(get_db),
):
    repo = StoreRepository(db)
    if organization_id:
        return await repo.get_by_organization(organization_id)
    return await repo.get_all()


@router.post("", response_model=APIResponse)
async def create_store(
    data: StoreCreate,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = StoreRepository(db)
    store_id = await repo.create(data)
    return APIResponse(message="Дэлгүүр нэмэгдлээ", data={"store_id": store_id})


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: int,
    admin: dict = Depends(require_admin_or_above),
    db: AsyncSession = Depends(get_db),
):
    repo = StoreRepository(db)
    store = await repo.get_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return store


@router.put("/{store_id}", response_model=APIResponse)
async def update_store(
    store_id: int,
    data: StoreUpdate,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = StoreRepository(db)
    success = await repo.update(store_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return APIResponse(message="Дэлгүүр шинэчлэгдлээ")


@router.delete("/{store_id}", response_model=APIResponse)
async def delete_store(
    store_id: int,
    admin: dict = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = StoreRepository(db)
    success = await repo.delete(store_id)
    if not success:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return APIResponse(message="Дэлгүүр устгагдлаа")
