from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from ..services.auth_service import AuthService
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="", tags=["Authentication"])

# --- МОДЕЛУУД ---

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    phone_number: str = None
    password: str
    full_name: str = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

# --- API ENDPOINTS ---

@router.post("/register")
async def register(user_data: UserCreate):
    # AuthService-ийн register_user функц async биш бол await-гүй дуудна
    # Хэрэв AuthService дотор async def register_user бол await AuthService.register_user(...)
    user_id = await AuthService.register_user(
        username=user_data.username, 
        email=user_data.email, 
        password=user_data.password, 
        phone_number=user_data.phone_number,
        full_name=user_data.full_name
    )
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Хэрэглэгч бүртгэхэд алдаа гарлаа. (Мэдээллийн сантай холбогдож чадсангүй)"
        )
        
    return {"message": "Хэрэглэгч амжилттай бүртгэгдлээ", "user_id": user_id}

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = AuthService.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх нэр эсвэл нууц үг буруу байна",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = AuthService.create_access_token(data={"sub": user["username"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "phone_number": user.get("phone_number")
        }
    }

# --- НУУЦ ҮГ СЭРГЭЭХ ХЭСЭГ (Эдгээрийг заавал нэмнэ) ---

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    # Имэйл рүү код илгээх
    success = await AuthService.generate_recovery_code(request.email)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ийм имэйлтэй хэрэглэгч олдсонгүй эсвэл имэйл илгээхэд алдаа гарлаа."
        )
    return {"message": "Сэргээх код имэйл рүү илгээгдлээ."}

@router.post("/verify-code")
async def verify_code(request: VerifyCodeRequest):
    # Код шалгах
    is_valid = AuthService.verify_recovery_code(request.email, request.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код буруу эсвэл хугацаа нь дууссан байна."
        )
    return {"message": "Код баталгаажлаа."}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    # Шинэ нууц үг хадгалах
    success = AuthService.reset_password(request.email, request.code, request.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нууц үг шинэчлэхэд алдаа гарлаа."
        )
    return {"message": "Нууц үг амжилттай шинэчлэгдлээ."}