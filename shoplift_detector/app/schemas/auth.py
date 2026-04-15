import re

from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    phone_number: str | None = None
    password: str
    full_name: str | None = None
    org_name: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Хэрэглэгчийн нэр 3-50 тэмдэгт байх ёстой")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Зөвхөн үсэг, тоо, _, - ашиглана")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Нууц үг хамгийн багадаа 8 тэмдэгт")
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]).{8,}$', v):
            raise ValueError("Том, жижиг үсэг, тоо, тусгай тэмдэгт агуулсан байх ёстой")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserBrief"


class UserBrief(BaseModel):
    username: str
    full_name: str | None = None
    role: str = "user"
    org_id: int | None = None
    org_name: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Нууц үг хамгийн багадаа 8 тэмдэгт")
        return v
