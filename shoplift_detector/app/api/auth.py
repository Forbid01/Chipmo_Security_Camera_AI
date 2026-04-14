from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from ..services.auth_service import AuthService
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Router тохиргоо
router = APIRouter(prefix="", tags=["Authentication"])

# --- МОДЕЛУУД (Pydantic Models) ---

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

class OrganizationCreate(BaseModel):
    name: str

class CameraCreate(BaseModel):
    name: str
    url: str
    type: str  # 'mac', 'phone', 'axis'
    organization_id: int

class CameraUpdate(BaseModel):
    name: str
    url: str
    type: str
    organization_id: int

class UserRoleUpdate(BaseModel):
    role: str

class UserOrgUpdate(BaseModel):
    organization_id: Optional[int] = None

# --- API ENDPOINTS ---

@router.post("/register")
async def register(user_data: UserCreate):
    """Шинэ хэрэглэгч бүртгэх"""
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
            detail="Бүртгэл амжилтгүй боллоо."
        )
        
    return {"message": "Хэрэглэгч амжилттай бүртгэгдлээ", "user_id": user_id}

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Нэвтрэх болон JWT Токен авах"""
    user = await AuthService.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нэвтрэх нэр эсвэл нууц үг буруу байна",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = await AuthService.create_access_token(
        data={
            "sub": user["username"],
            "org_id": user.get("organization_id"),
            "role": user.get("role", "user")
        }
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "role": user.get("role", "user"),
            "org_id": user.get("organization_id"),
            "org_name": user.get("organization_name"),
        }
    }

# --- НУУЦ ҮГ СЭРГЭЭХ ---

@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest):
    success = await AuthService.generate_recovery_code(data.email)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Хэрэглэгч олдсонгүй эсвэл имэйл илгээхэд алдаа гарлаа."
        )
    return {"message": "Сэргээх код имэйл рүү илгээгдлээ."}

@router.post("/verify-code")
@limiter.limit("5/minute")
async def verify_code(request: Request, data: VerifyCodeRequest):
    is_valid = await AuthService.verify_recovery_code(data.email, data.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код буруу эсвэл хугацаа нь дууссан байна."
        )
    return {"message": "Код баталгаажлаа."}

@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest):
    success = await AuthService.reset_password(data.email, data.code, data.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нууц үг шинэчлэхэд алдаа гарлаа."
        )
    return {"message": "Нууц үг амжилттай шинэчлэгдлээ."}

# --- АДМИН ҮЙЛДЛҮҮД (Role-based Access) ---

# 1. Байгууллага удирдах (GET, POST, DELETE)

@router.get("/admin/organizations")
async def get_organizations(current_user: dict = Depends(AuthService.get_current_user)):
    """Бүх байгууллагын жагсаалтыг харах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    return await AuthService.get_all_organizations()

@router.post("/admin/organizations")
async def create_org(
    org_data: OrganizationCreate, 
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Шинэ байгууллага үүсгэх"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Танд байгууллага нэмэх эрх байхгүй!")
    
    org_id = await AuthService.create_organization(org_data.name)
    return {"message": "Байгууллага нэмэгдлээ", "org_id": org_id}

@router.delete("/admin/organizations/{org_id}")
async def delete_organization(
    org_id: int, 
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Байгууллага устгах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    
    success = await AuthService.delete_organization(org_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Байгууллага олдсонгүй")
    return {"message": "Байгууллага амжилттай устгагдлаа"}

# 2. Камер удирдах (GET, POST, DELETE)

@router.get("/admin/cameras")
async def get_cameras(current_user: dict = Depends(AuthService.get_current_user)):
    """Бүх камерын жагсаалтыг харах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    return await AuthService.get_all_cameras()

@router.post("/admin/cameras")
async def add_camera_to_org(
    cam_data: CameraCreate, 
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Байгууллагад камер холбох"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Танд камер нэмэх эрх байхгүй!")
    
    cam_id = await AuthService.add_camera(
        name=cam_data.name,
        url=cam_data.url,
        cam_type=cam_data.type,
        org_id=cam_data.organization_id
    )
    return {"message": "Камер амжилттай холбогдлоо", "cam_id": cam_id}

@router.delete("/admin/cameras/{cam_id}")
async def delete_camera(
    cam_id: int, 
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Камер устгах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    
    success = await AuthService.delete_camera(cam_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Камер олдсонгүй")
    return {"message": "Камер амжилттай устгагдлаа"}

@router.put("/admin/cameras/{cam_id}")
async def update_camera(
    cam_id: int,
    cam_data: CameraUpdate,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Камерын мэдээлэл засах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    success = await AuthService.update_camera(cam_id, cam_data.name, cam_data.url, cam_data.type, cam_data.organization_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Камер олдсонгүй")
    return {"message": "Камер амжилттай шинэчлэгдлээ"}

# 3. Хэрэглэгч удирдах (GET, PUT, DELETE)

@router.get("/admin/users")
async def get_users(current_user: dict = Depends(AuthService.get_current_user)):
    """Бүх хэрэглэгчдийн жагсаалт"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    return await AuthService.get_all_users()

@router.put("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Хэрэглэгчийн эрх (role) өөрчлөх"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    success = await AuthService.update_user_role(user_id, data.role)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Алдаа гарлаа")
    return {"message": "Хэрэглэгчийн эрх шинэчлэгдлээ"}

@router.put("/admin/users/{user_id}/organization")
async def update_user_org(
    user_id: int,
    data: UserOrgUpdate,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Хэрэглэгчийг байгууллагад хуваарилах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    success = await AuthService.update_user_organization(user_id, data.organization_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Алдаа гарлаа")
    return {"message": "Хэрэглэгч байгууллагад хуваарилагдлаа"}

@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Хэрэглэгч идэвхгүй болгох"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    target = await AuthService.get_user_by_id(user_id)
    if target and target.get("username") == current_user.get("username"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Өөрийгөө устгах боломжгүй")
    success = await AuthService.deactivate_user(user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хэрэглэгч олдсонгүй")
    return {"message": "Хэрэглэгч идэвхгүй болгогдлоо"}

# 4. Статистик (Dashboard)

@router.get("/admin/stats")
async def get_stats(current_user: dict = Depends(AuthService.get_current_user)):
    """Системийн ерөнхий статистик"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    return await AuthService.get_stats()

# 5. Alert удирдах (GET, PUT, DELETE)

@router.get("/admin/alerts")
async def get_admin_alerts(
    organization_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Бүх alert-уудыг харах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    return await AuthService.get_all_alerts_admin(organization_id, limit, offset)

@router.put("/admin/alerts/{alert_id}/reviewed")
async def mark_alert_reviewed(
    alert_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Alert-ыг шалгасан гэж тэмдэглэх"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    success = await AuthService.mark_alert_reviewed(alert_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert олдсонгүй")
    return {"message": "Alert шалгагдсан гэж тэмдэглэгдлээ"}

@router.delete("/admin/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    current_user: dict = Depends(AuthService.get_current_user)
):
    """Alert устгах"""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Эрх хүрэлцэхгүй")
    success = await AuthService.delete_alert(alert_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert олдсонгүй")
    return {"message": "Alert устгагдлаа"}