import random
import string
import logging
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from ..core.security import verify_password, get_password_hash, create_access_token
from ..db.repository.users import UserRepository
from .email_service import send_otp_email

logger = logging.getLogger(__name__)
user_repo = UserRepository()

class AuthService:
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

    # --- НУУЦ ҮГ СЭРГЭЭХ ЛОГИК ---

    @classmethod
    async def generate_recovery_code(cls, email: str):
        """1. OTP үүсгэж, DB-д хадгалаад имэйл илгээх"""
        user = user_repo.get_by_email(email)
        if not user:
            logger.warning(f"Password recovery attempt for non-existent email: {email}")
            return False

        # 6 оронтой тоон код үүсгэх
        otp_code = ''.join(random.choices(string.digits, k=6))
        # 15 минутын дараа хүчингүй болно
        expiry = datetime.utcnow() + timedelta(minutes=15)

        # DB-д OTP хадгалах
        user_repo.update_recovery_data(user['id'], otp_code, expiry)

        # Бодит имэйл илгээх
        success = await send_otp_email(email, otp_code)
        return success

    @classmethod
    def verify_recovery_code(cls, email: str, code: str):
        """2. Хэрэглэгчийн кодыг DB-тэй тулгах"""
        user = user_repo.get_by_email(email)
        if not user:
            return False

        # DB-ээс ирсэн утгуудыг шалгах
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
        # Аюулгүй байдлын үүднээс кодыг дахин шалгана
        if not cls.verify_recovery_code(email, code):
            return False

        user = user_repo.get_by_email(email)
        if not user:
            return False

        hashed_pwd = get_password_hash(new_password)

        # Нууц үг шинэчлэх болон OTP датаг цэвэрлэх
        user_repo.update_password(user['id'], hashed_pwd)
        user_repo.clear_recovery_data(user['id'])
        
        return True