import os
from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

load_dotenv()

# Тохиргооны утгуудыг энд нэгтгэе (Function-уудын дээр байвал илүү цэгцтэй)
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-hidden-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = "30"

# 1. OAuth2 схемийг тодорхойлох (Хувьсагчийн нэрийг oauth2_scheme болгох)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# 2. Нууц үг шифрлэх тохиргоо
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_current_user(token: str = Depends(oauth2_scheme)):
    """Токеныг шалгах Middleware"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Хандах эрхгүй байна. Нэвтрэнэ үү!",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # JWT токенийг тайлж унших
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except (jwt.PyJWTError, jwt.ExpiredSignatureError):
        # Хугацаа дууссан эсвэл буруу токен байвал алдаа шиднэ
        raise credentials_exception

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt