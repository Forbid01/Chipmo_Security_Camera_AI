import random
import string
from datetime import UTC, datetime, timedelta
from typing import Annotated

from app.core.rate_limiting import RateLimits, limiter
from app.core.security import (
    CurrentUser,
    clear_auth_cookie,
    create_access_token,
    get_password_hash,
    set_auth_cookie,
    validate_password_strength,
    verify_password,
)
from app.db.repository.tenants import TenantRepository
from app.db.repository.users import UserRepository
from app.db.session import DB
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserBrief,
    UserCreate,
    VerifyCodeRequest,
)
from app.schemas.common import APIResponse
from app.services.email_service import send_otp_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter()
# Keep `limiter` re-exported so existing decorators in this module
# continue to work without change; underlying instance is now the
# shared Redis-backed limiter from app.core.rate_limiting.
__all__ = ["router", "limiter", "RateLimits"]

LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


@router.post("/register", response_model=APIResponse)
async def register(user_data: UserCreate, db: DB):
    repo = UserRepository(db)
    existing = await repo.get_by_identifier(user_data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Хэрэглэгчийн нэр бүртгэлтэй байна")

    existing_email = await repo.get_by_email(user_data.email)
    if existing_email:
        raise HTTPException(status_code=400, detail="Имэйл бүртгэлтэй байна")

    org_id = None
    if user_data.org_name:
        org_id = await repo.get_or_create_organization(user_data.org_name.strip())

    hashed_pwd = get_password_hash(user_data.password)
    user_id = await repo.create(
        username=user_data.username,
        email=user_data.email,
        phone_number=user_data.phone_number,
        hashed_password=hashed_pwd,
        full_name=user_data.full_name,
        organization_id=org_id,
    )
    return APIResponse(message="Хэрэглэгч амжилттай бүртгэгдлээ", data={"user_id": user_id})


@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    form_data: LoginForm,
    db: DB,
):
    repo = UserRepository(db)
    user = await repo.get_by_identifier(form_data.username)

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх нэр эсвэл нууц үг буруу байна",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_repo = TenantRepository(db)
    tenant_id = await tenant_repo.get_tenant_id_for_organization(
        user.get("organization_id")
    )
    token_data = {
        "sub": user["username"],
        "role": user.get("role", "user"),
        "org_id": user.get("organization_id"),
        "user_id": user.get("id"),
        "tenant_id": tenant_id,
    }
    access_token = create_access_token(data=token_data)

    set_auth_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        user=UserBrief(
            username=user["username"],
            full_name=user.get("full_name"),
            role=user.get("role", "user"),
            org_id=user.get("organization_id"),
            org_name=user.get("organization_name"),
        ),
    )


@router.post("/logout", response_model=APIResponse)
async def logout(response: Response):
    clear_auth_cookie(response)
    return APIResponse(message="Амжилттай гарлаа")


@router.get("/me")
async def get_me(current_user: CurrentUser, db: DB):
    repo = UserRepository(db)
    user = await repo.get_by_identifier(current_user["username"])
    if not user:
        raise HTTPException(status_code=404, detail="Хэрэглэгч олдсонгүй")
    return {
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role", "user"),
        "org_id": user.get("organization_id"),
        "org_name": user.get("organization_name"),
    }


@router.post("/forgot-password", response_model=APIResponse)
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: DB):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        # Don't reveal if email exists
        return APIResponse(message="Хэрэв имэйл бүртгэлтэй бол сэргээх код илгээгдлээ")

    otp_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = datetime.now(UTC) + timedelta(minutes=15)
    await repo.update_recovery_data(user["id"], otp_code, expiry)
    await send_otp_email(data.email, otp_code)
    return APIResponse(message="Сэргээх код имэйл рүү илгээгдлээ")


@router.post("/verify-code", response_model=APIResponse)
@limiter.limit("5/minute")
async def verify_code(request: Request, data: VerifyCodeRequest, db: DB):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        raise HTTPException(status_code=400, detail="Код буруу")

    db_code = user.get("recovery_code")
    db_expiry = user.get("recovery_code_expires")
    if db_code != data.code or not db_expiry or db_expiry < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")

    return APIResponse(message="Код баталгаажлаа")


@router.post("/reset-password", response_model=APIResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: DB):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        raise HTTPException(status_code=400, detail="Алдаа гарлаа")

    db_code = user.get("recovery_code")
    db_expiry = user.get("recovery_code_expires")
    if db_code != data.code or not db_expiry or db_expiry < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")

    validate_password_strength(data.new_password)
    hashed_pwd = get_password_hash(data.new_password)
    await repo.update_password(user["id"], hashed_pwd)
    await repo.clear_recovery_data(user["id"])
    return APIResponse(message="Нууц үг амжилттай шинэчлэгдлээ")
