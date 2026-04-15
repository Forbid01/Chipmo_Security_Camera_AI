from app.core.security import AdminOrAbove, SuperAdmin
from app.db.repository.stores import StoreRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from app.schemas.store import StoreCreate, StoreResponse, StoreUpdate
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("")
async def list_stores(admin: AdminOrAbove, db: DB, organization_id: int | None = None):
    repo = StoreRepository(db)
    if organization_id:
        return await repo.get_by_organization(organization_id)
    return await repo.get_all()


@router.post("", response_model=APIResponse)
async def create_store(data: StoreCreate, admin: SuperAdmin, db: DB):
    repo = StoreRepository(db)
    store_id = await repo.create(data)
    return APIResponse(message="Дэлгүүр нэмэгдлээ", data={"store_id": store_id})


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(store_id: int, admin: AdminOrAbove, db: DB):
    repo = StoreRepository(db)
    store = await repo.get_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return store


@router.put("/{store_id}", response_model=APIResponse)
async def update_store(store_id: int, data: StoreUpdate, admin: SuperAdmin, db: DB):
    repo = StoreRepository(db)
    success = await repo.update(store_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return APIResponse(message="Дэлгүүр шинэчлэгдлээ")


@router.delete("/{store_id}", response_model=APIResponse)
async def delete_store(store_id: int, admin: SuperAdmin, db: DB):
    repo = StoreRepository(db)
    success = await repo.delete(store_id)
    if not success:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")
    return APIResponse(message="Дэлгүүр устгагдлаа")
