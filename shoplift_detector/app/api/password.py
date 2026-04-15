from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..services.auth_service import AuthService

router = APIRouter(prefix="/", tags=["password-recovery"])

# --- Request Models ---
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

# --- Endpoints ---

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    """1. Хэрэглэгчийн имэйл рүү OTP код илгээх"""
    # AuthService ашиглан код үүсгэж, DB-д хадгалаад имэйл илгээнэ
    # background_tasks ашиглаж болох ч generate_recovery_code өөрөө async байгаа
    success = await AuthService.generate_recovery_code(request.email)

    if not success:
        # Аюулгүй байдлын үүднээс "Имэйл байхгүй" гэж хэлэхгүйгээр
        # "Хэрэв бүртгэлтэй бол илгээгдлээ" гэсэн утгатай хариу өгөх нь дээр
        return {"message": "Хэрэв имэйл бүртгэлтэй бол сэргээх код илгээгдлээ."}

    return {"message": "Сэргээх код имэйл хаяг руу илгээгдлээ."}

@router.post("/verify-code")
async def verify_code(request: VerifyCodeRequest):
    """2. Хэрэглэгчийн оруулсан кодыг баталгаажуулах"""
    is_valid = AuthService.verify_recovery_code(request.email, request.code)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код буруу эсвэл хугацаа нь дууссан байна."
        )

    return {"message": "Код амжилттай баталгаажлаа."}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """3. Шинэ нууц үгийг hash-лаад DB-д хадгалах"""
    success = AuthService.reset_password(
        email=request.email,
        code=request.code,
        new_password=request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нууц үг шинэчлэх боломжгүй. Кодоо дахин шалгана уу."
        )

    return {"message": "Нууц үг амжилттай шинэчлэгдлээ."}
