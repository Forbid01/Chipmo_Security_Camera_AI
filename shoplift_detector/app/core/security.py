import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from app.core.config import settings
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

MIN_PASSWORD_LENGTH = 8
PASSWORD_PATTERN = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]).{8,}$'
)

COOKIE_NAME = "access_token"


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Нууц үг хамгийн багадаа {MIN_PASSWORD_LENGTH} тэмдэгт байх ёстой."
        )
    if not PASSWORD_PATTERN.match(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нууц үг том, жижиг үсэг, тоо, тусгай тэмдэгт агуулсан байх ёстой."
        )


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def _bcrypt_secret(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes. Truncate explicitly so local
    # bcrypt>=5 and older production bcrypt behave the same way.
    return password.encode("utf-8")[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _bcrypt_secret(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _extract_token(request: Request, bearer_token: str | None = None) -> str | None:
    """Extract token from cookie first, then Authorization header."""
    # 1. Try httpOnly cookie
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    # 2. Try Authorization header (for API clients / mobile)
    if bearer_token:
        return bearer_token
    return None


def _decode_token(token: str) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Хандах эрхгүй байна.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return {
            "username": username,
            "org_id": payload.get("org_id"),
            "role": payload.get("role"),
            "user_id": payload.get("user_id"),
            "tenant_id": payload.get("tenant_id"),
            "iat": payload.get("iat"),
        }
    except (jwt.PyJWTError, jwt.ExpiredSignatureError) as e:
        raise credentials_exception from e


BearerToken = Annotated[str | None, Depends(oauth2_scheme)]


async def get_current_user(
    request: Request,
    bearer_token: BearerToken,
) -> dict:
    token = _extract_token(request, bearer_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх шаардлагатай.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(token)


async def get_current_user_optional(
    request: Request,
    bearer_token: BearerToken,
) -> dict | None:
    token = _extract_token(request, bearer_token)
    if not token:
        return None
    try:
        return _decode_token(token)
    except HTTPException:
        return None


CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(get_current_user_optional)]


def require_role(*roles: str):
    """Dependency factory for role-based access control."""
    async def checker(current_user: CurrentUser) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Эрх хүрэлцэхгүй"
            )
        return current_user
    return checker


async def require_super_admin(current_user: CurrentUser) -> dict:
    if current_user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Зөвхөн super admin эрхтэй"
        )
    return current_user


async def require_admin_or_above(current_user: CurrentUser) -> dict:
    if current_user.get("role") not in ("super_admin", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Админ эрх шаардлагатай"
        )
    return current_user


SuperAdmin = Annotated[dict, Depends(require_super_admin)]
AdminOrAbove = Annotated[dict, Depends(require_admin_or_above)]
