import random
import string
import logging
import jwt 
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status, Depends

from ..core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    validate_password_strength,
    oauth2_scheme,
    SECRET_KEY,
    ALGORITHM
)
from ..db.repository.users import UserRepository
from .email_service import send_otp_email

logger = logging.getLogger(__name__)
user_repo = UserRepository()

class AuthService:
    
    # --- БҮРТГЭЛ БОЛОН НЭВТРЭЛТ ---

    @classmethod
    async def register_user(cls, username, email, password, phone_number=None, full_name=None, role="user"):
        """Шинэ хэрэглэгч бүртгэх"""
        validate_password_strength(password)
        if await user_repo.get_by_identifier(username) or await user_repo.get_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Хэрэглэгчийн нэр эсвэл имэйл бүртгэлтэй байна."
            )
        hashed_pwd = get_password_hash(password)
        # Repository-ийн create функц чинь 'role' хүлээж авдаг байх шаардлагатай
        user_id = await user_repo.create(
            username=username, 
            email=email, 
            phone_number=phone_number, 
            hashed_password=hashed_pwd, 
            full_name=full_name,
            role=role
        )
        return user_id

    @classmethod
    async def authenticate_user(cls, identifier, password):
        """Нэвтрэх үед хэрэглэгчийг баталгаажуулах"""
        user = await user_repo.get_by_identifier(identifier)
        if not user or not verify_password(password, user['hashed_password']):
            return False
        return user

    @classmethod
    async def create_access_token(cls, data: dict):
        """JWT Token үүсгэх"""
        return create_access_token(data)

    @staticmethod
    async def get_current_user(token: str = Depends(oauth2_scheme)):
        """Токен уншиж хэрэглэгчийн мэдээллийг (role, org_id) буцаах"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            org_id: int = payload.get("org_id")
            role: str = payload.get("role")
            
            if username is None:
                raise HTTPException(status_code=401, detail="Токен хүчингүй")
                
            return {
                "username": username,
                "org_id": org_id,
                "role": role
            }
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Токен хүчингүй эсвэл хугацаа дууссан байна"
            )

    # --- АДМИН БОЛОН БАЙГУУЛЛАГЫН ҮЙЛДЛҮҮД (CRUD) ---

    @staticmethod
    async def create_organization(name: str):
        """Шинэ байгууллага үүсгэх"""
        return await user_repo.create_organization(name)

    @staticmethod
    async def get_all_organizations():
        """Бүх байгууллагын жагсаалтыг авах (DashboardAdmin-д хэрэгтэй)"""
        return await user_repo.get_all_organizations()

    @staticmethod
    async def delete_organization(org_id: int):
        """Байгууллага устгах"""
        return await user_repo.delete_organization(org_id)

    @staticmethod
    async def add_camera(name, url, cam_type, org_id):
        """Шинэ камер бүртгэх"""
        return await user_repo.add_camera(name, url, cam_type, org_id)

    @staticmethod
    async def get_all_cameras():
        """Бүх камерын жагсаалтыг авах (DashboardAdmin-д хэрэгтэй)"""
        return await user_repo.get_all_cameras()

    @staticmethod
    async def delete_camera(cam_id: int):
        """Камер устгах"""
        return await user_repo.delete_camera(cam_id)

    # --- НУУЦ ҮГ СЭРГЭЭХ ЛОГИК (OTP) ---

    @classmethod
    async def generate_recovery_code(cls, email: str):
        user = await user_repo.get_by_email(email)
        if not user:
            return False

        otp_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        expiry = datetime.now(timezone.utc) + timedelta(minutes=15)

        await user_repo.update_recovery_data(user['id'], otp_code, expiry)
        success = await send_otp_email(email, otp_code)
        return success

    @classmethod
    async def verify_recovery_code(cls, email: str, code: str):
        user = await user_repo.get_by_email(email)
        if not user: return False

        db_code = user.get('recovery_code')
        db_expiry = user.get('recovery_code_expires')

        if (db_code == code and db_expiry and db_expiry > datetime.now(timezone.utc)):
            return True
        return False

    @classmethod
    async def reset_password(cls, email: str, code: str, new_password: str):
        if not await cls.verify_recovery_code(email, code):
            return False

        user = await user_repo.get_by_email(email)
        if not user: return False

        validate_password_strength(new_password)
        hashed_pwd = get_password_hash(new_password)
        await user_repo.update_password(user['id'], hashed_pwd)
        await user_repo.clear_recovery_data(user['id'])
        return True