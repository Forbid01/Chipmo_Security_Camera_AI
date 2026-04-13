import random
import string
import logging
import jwt # Токен задлахад хэрэгтэй
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Depends

# Core болон Security-ээс хэрэгтэй функцүүдээ импортлох
from ..core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    oauth2_scheme, # Token-г Header-ээс салгаж авах dependency
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
    async def register_user(cls, username, email, password, phone_number=None, full_name=None):
        """Шинэ хэрэглэгч бүртгэх"""
        if user_repo.get_by_identifier(username) or user_repo.get_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Хэрэглэгчийн нэр эсвэл имэйл бүртгэлтэй байна."
            )
        hashed_pwd = get_password_hash(password)
        user_id = user_repo.create(
            username=username, 
            email=email, 
            phone_number=phone_number, 
            hashed_password=hashed_pwd, 
            full_name=full_name
        )
        return user_id

    @classmethod
    def authenticate_user(cls, identifier, password):
        """Нэвтрэх үед хэрэглэгчийг баталгаажуулах"""
        user = user_repo.get_by_identifier(identifier)
        if not user or not verify_password(password, user['hashed_password']):
            return False
        return user

    @classmethod
    def create_access_token(cls, data: dict):
        """JWT Token үүсгэх"""
        return create_access_token(data)

    @staticmethod
    def get_current_user(token: str = Depends(oauth2_scheme)):
        """
        Токен уншиж хэрэглэгчийн мэдээллийг (role, org_id) буцаах. 
        Энэ функцийг Router дээр Depends болгож ашиглана.
        """
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

    # --- НУУЦ ҮГ СЭРГЭЭХ ЛОГИК ---

    @classmethod
    async def generate_recovery_code(cls, email: str):
        """1. OTP үүсгэж, DB-д хадгалаад имэйл илгээх"""
        user = user_repo.get_by_email(email)
        if not user:
            logger.warning(f"Password recovery attempt for non-existent email: {email}")
            return False

        otp_code = ''.join(random.choices(string.digits, k=6))
        expiry = datetime.utcnow() + timedelta(minutes=15)

        user_repo.update_recovery_data(user['id'], otp_code, expiry)
        success = await send_otp_email(email, otp_code)
        return success

    @classmethod
    def verify_recovery_code(cls, email: str, code: str):
        """2. Хэрэглэгчийн кодыг DB-тэй тулгах"""
        user = user_repo.get_by_email(email)
        if not user:
            return False

        db_code = user.get('recovery_code')
        db_expiry = user.get('recovery_code_expires')

        if (db_code == code and 
            db_expiry and 
            db_expiry > datetime.utcnow()):
            return True
        
        return False

    @classmethod
    def reset_password(cls, email: str, code: str, new_password: str):
        """3. Код зөв бол нууц үгийг шинэчлэх"""
        if not cls.verify_recovery_code(email, code):
            return False

        user = user_repo.get_by_email(email)
        if not user:
            return False

        hashed_pwd = get_password_hash(new_password)
        user_repo.update_password(user['id'], hashed_pwd)
        user_repo.clear_recovery_data(user['id'])
        return True

    # --- АДМИН БОЛОН БАЙГУУЛЛАГЫН ҮЙЛДЛҮҮД ---

    @staticmethod
    def create_organization(name: str):
        return user_repo.create_organization(name)

    @staticmethod
    def add_camera(name, url, cam_type, org_id):
        return user_repo.add_camera(name, url, cam_type, org_id)

    @staticmethod
    def get_organizations():
        return user_repo.get_all_organizations()