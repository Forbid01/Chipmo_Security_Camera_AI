from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import (
    verify_password, get_password_hash, create_access_token,
    validate_password_strength, get_current_user, set_auth_cookie, clear_auth_cookie,
)
from app.db.session import get_db
from app.db.repository.users import UserRepository
from app.schemas.auth import (
    UserCreate, TokenResponse, UserBrief,
    ForgotPasswordRequest, VerifyCodeRequest, ResetPasswordRequest,
)
from app.schemas.common import APIResponse
from app.services.email_service import send_otp_email

import random
import string
from datetime import datetime, timedelta, timezone

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=APIResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    existing = await repo.get_by_identifier(user_data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Хэрэглэгчийн нэр бүртгэлтэй байна")

    existing_email = await repo.get_by_email(user_data.email)
    if existing_email:
        raise HTTPException(status_code=400, detail="Имэйл бүртгэлтэй байна")

    hashed_pwd = get_password_hash(user_data.password)
    user_id = await repo.create(
        username=user_data.username,
        email=user_data.email,
        phone_number=user_data.phone_number,
        hashed_password=hashed_pwd,
        full_name=user_data.full_name,
    )
    return APIResponse(message="Хэрэглэгч амжилттай бүртгэгдлээ", data={"user_id": user_id})


@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_identifier(form_data.username)

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх нэр эсвэл нууц үг буруу байна",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": user["username"],
        "role": user.get("role", "user"),
        "org_id": user.get("organization_id"),
        "user_id": user.get("id"),
    }
    access_token = create_access_token(data=token_data)

    # Set httpOnly cookie
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
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        # Don't reveal if email exists
        return APIResponse(message="Хэрэв имэйл бүртгэлтэй бол сэргээх код илгээгдлээ")

    otp_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
    await repo.update_recovery_data(user["id"], otp_code, expiry)
    await send_otp_email(data.email, otp_code)
    return APIResponse(message="Сэргээх код имэйл рүү илгээгдлээ")


@router.post("/verify-code", response_model=APIResponse)
@limiter.limit("5/minute")
async def verify_code(request: Request, data: VerifyCodeRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        raise HTTPException(status_code=400, detail="Код буруу")

    db_code = user.get("recovery_code")
    db_expiry = user.get("recovery_code_expires")
    if db_code != data.code or not db_expiry or db_expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")

    return APIResponse(message="Код баталгаажлаа")


@router.post("/reset-password", response_model=APIResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(data.email)
    if not user:
        raise HTTPException(status_code=400, detail="Алдаа гарлаа")

    db_code = user.get("recovery_code")
    db_expiry = user.get("recovery_code_expires")
    if db_code != data.code or not db_expiry or db_expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Код буруу эсвэл хугацаа дууссан")

    validate_password_strength(data.new_password)
    hashed_pwd = get_password_hash(data.new_password)
    await repo.update_password(user["id"], hashed_pwd)
    await repo.clear_recovery_data(user["id"])
    return APIResponse(message="Нууц үг амжилттай шинэчлэгдлээ")
