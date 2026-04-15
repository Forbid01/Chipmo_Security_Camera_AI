from app.core.security import SuperAdmin
from app.db.repository.stores import StoreRepository
from app.db.repository.users import UserRepository
from app.db.session import DB
from app.schemas.common import APIResponse, StatsResponse
from app.schemas.organization import OrganizationCreate
from app.schemas.user import UserOrgUpdate, UserRoleUpdate
from fastapi import APIRouter, HTTPException

router = APIRouter()

VALID_ROLES = {"user", "admin", "super_admin"}


# --- Organizations ---

@router.get("/organizations")
async def get_organizations(admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    return await repo.get_all_organizations()


@router.post("/organizations", response_model=APIResponse)
async def create_organization(data: OrganizationCreate, admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    org_id = await repo.create_organization(data.name)
    return APIResponse(message="Байгууллага нэмэгдлээ", data={"org_id": org_id})


@router.delete("/organizations/{org_id}", response_model=APIResponse)
async def delete_organization(org_id: int, admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    success = await repo.delete_organization(org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Байгууллага олдсонгүй")
    return APIResponse(message="Байгууллага устгагдлаа")


# --- Users ---

@router.get("/users")
async def get_users(admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    return await repo.get_all_users()


@router.put("/users/{user_id}/role", response_model=APIResponse)
async def update_user_role(user_id: int, data: UserRoleUpdate, admin: SuperAdmin, db: DB):
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role '{data.role}' буруу байна")
    repo = UserRepository(db)
    success = await repo.update_user_role(user_id, data.role)
    if not success:
        raise HTTPException(status_code=400, detail="Алдаа гарлаа")
    return APIResponse(message="Хэрэглэгчийн эрх шинэчлэгдлээ")


@router.put("/users/{user_id}/organization", response_model=APIResponse)
async def update_user_org(user_id: int, data: UserOrgUpdate, admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    success = await repo.update_user_organization(user_id, data.organization_id)
    if not success:
        raise HTTPException(status_code=400, detail="Алдаа гарлаа")
    return APIResponse(message="Хэрэглэгч байгууллагад хуваарилагдлаа")


@router.delete("/users/{user_id}", response_model=APIResponse)
async def delete_user(user_id: int, admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    target = await repo.get_user_by_id(user_id)
    if target and target.get("username") == admin.get("username"):
        raise HTTPException(status_code=400, detail="Өөрийгөө устгах боломжгүй")
    success = await repo.deactivate_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Хэрэглэгч олдсонгүй")
    return APIResponse(message="Хэрэглэгч идэвхгүй болгогдлоо")


# --- Stats ---

@router.get("/stats", response_model=StatsResponse)
async def get_stats(admin: SuperAdmin, db: DB):
    repo = UserRepository(db)
    stats = await repo.get_stats()
    store_repo = StoreRepository(db)
    store_count = await store_repo.count()
    return StatsResponse(
        users=stats.get("users", 0),
        organizations=stats.get("organizations", 0),
        stores=store_count,
        cameras=stats.get("cameras", 0),
        alerts=stats.get("alerts", 0),
    )
