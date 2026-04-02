import logging
import psycopg2.extras
from datetime import datetime
from app.db.base import BaseDB

logger = logging.getLogger(__name__)

class UserRepository(BaseDB):
    def __init__(self):
        super().__init__()
        self._create_table()

    def _create_table(self):
        """Хэрэглэгчийн хүснэгт үүсгэх (OTP баганууд нэмэгдсэн)"""
        query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            phone_number VARCHAR(20) UNIQUE,
            hashed_password TEXT NOT NULL,
            full_name VARCHAR(100),
            recovery_code VARCHAR(10),
            recovery_code_expires TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    conn.commit()
        except Exception as e:
            logger.error(f"Table Creation Error: {e}")

    def update_recovery_data(self, user_id: int, code: str, expiry: datetime):
        """OTP код болон хүчинтэй хугацааг шинэчлэх"""
        query = """
        UPDATE users 
        SET recovery_code = %s, recovery_code_expires = %s 
        WHERE id = %s
        """
        return self._execute_update(query, (code, expiry, user_id))

    def clear_recovery_data(self, user_id: int):
        """Ашиглаж дууссаны дараа кодыг цэвэрлэх"""
        query = """
        UPDATE users 
        SET recovery_code = NULL, recovery_code_expires = NULL 
        WHERE id = %s
        """
        # Ганц параметр дамжуулж байгаа тул (user_id,) таслал заавал хэрэгтэй
        return self._execute_update(query, (user_id,))

    def update_password(self, user_id: int, new_hashed_password: str):
        """Нууц үг шинэчлэх"""
        query = "UPDATE users SET hashed_password = %s WHERE id = %s"
        return self._execute_update(query, (new_hashed_password, user_id))

    def create(self, username, email, phone_number, hashed_password, full_name=None):
        """Шинэ хэрэглэгч бүртгэх"""
        query = """
        INSERT INTO users (username, email, phone_number, hashed_password, full_name)
        VALUES (%s, %s, %s, %s, %s) RETURNING id;
        """
        params = (username, email, phone_number, hashed_password, full_name)
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    user_id = cur.fetchone()[0]
                    conn.commit()
                    return user_id
        except Exception as e:
            logger.error(f"User Creation Error: {e}")
            return None

    def get_by_id(self, user_id: int):
        query = "SELECT * FROM users WHERE id = %s"
        return self._execute_fetch_one(query, (user_id,))

    def get_by_email(self, email: str):
        """Имэйлээр хайх"""
        query = "SELECT * FROM users WHERE email = %s"
        return self._execute_fetch_one(query, (email,))

    def get_by_identifier(self, identifier: str):
        """Нэвтрэх нэр эсвэл Имэйлээр хайх"""
        query = "SELECT * FROM users WHERE (username = %s OR email = %s) AND is_active = TRUE"
        return self._execute_fetch_one(query, (identifier, identifier))

    def set_active_status(self, user_id: int, status: bool):
        query = "UPDATE users SET is_active = %s WHERE id = %s"
        return self._execute_update(query, (status, user_id))

    def _execute_fetch_one(self, query, params):
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Database Fetch Error: {e}")
            return None

    def _execute_update(self, query, params):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Database Update Error: {e}")
            return False