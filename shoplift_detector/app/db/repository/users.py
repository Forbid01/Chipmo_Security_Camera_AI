import logging
import psycopg2.extras
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.db.base import BaseDB

logger = logging.getLogger(__name__)

class UserRepository(BaseDB):
    def __init__(self):
        super().__init__()
        self._create_table()

    def _create_table(self):
        """Өгөгдлийн сангийн хүснэгтүүдийг үүсгэх (Multi-tenant бүтэц)"""
        queries = [
            # 1. Байгууллагууд (Organizations)
            """
            CREATE TABLE IF NOT EXISTS organizations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # 2. Хэрэглэгчид (Users)
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                phone_number VARCHAR(20) UNIQUE,
                hashed_password TEXT NOT NULL,
                full_name VARCHAR(100),
                role VARCHAR(20) DEFAULT 'user', -- 'super_admin' эсвэл 'user'
                organization_id INTEGER REFERENCES organizations(id),
                recovery_code VARCHAR(10),
                recovery_code_expires TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # 3. Камерууд (Cameras)
            """
            CREATE TABLE IF NOT EXISTS cameras (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                url TEXT NOT NULL,
                type VARCHAR(20), -- 'mac', 'phone', 'axis' гэх мэт
                organization_id INTEGER REFERENCES organizations(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        ]
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for q in queries:
                        cur.execute(q)
                    conn.commit()
        except Exception as e:
            logger.error(f"Table Creation Error: {e}")

    # --- Хэрэглэгчийн Үйлдлүүд ---

    def create(self, username, email, phone_number, hashed_password, full_name=None, organization_id=None, role='user') -> Optional[int]:
        """Шинэ хэрэглэгч бүртгэх"""
        query = """
        INSERT INTO users (username, email, phone_number, hashed_password, full_name, organization_id, role)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """
        params = (username, email, phone_number, hashed_password, full_name, organization_id, role)
        return self._execute_returning_id(query, params)

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM users WHERE id = %s"
        return self._execute_fetch_one(query, (user_id,))

    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM users WHERE email = %s"
        return self._execute_fetch_one(query, (email,))

    def get_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Нэвтрэх нэр эсвэл Имэйлээр идэвхтэй хэрэглэгчийг хайх"""
        query = "SELECT * FROM users WHERE (username = %s OR email = %s) AND is_active = TRUE"
        return self._execute_fetch_one(query, (identifier, identifier))

    def set_active_status(self, user_id: int, status: bool) -> bool:
        query = "UPDATE users SET is_active = %s WHERE id = %s"
        return self._execute_update(query, (status, user_id))

    # --- Нууц үг Сэргээх болон Шинэчлэх ---

    def update_recovery_data(self, user_id: int, code: str, expiry: datetime) -> bool:
        """OTP код болон хүчинтэй хугацааг хадгалах"""
        query = "UPDATE users SET recovery_code = %s, recovery_code_expires = %s WHERE id = %s"
        return self._execute_update(query, (code, expiry, user_id))

    def clear_recovery_data(self, user_id: int) -> bool:
        """Ашиглаж дууссан OTP кодыг цэвэрлэх"""
        query = "UPDATE users SET recovery_code = NULL, recovery_code_expires = NULL WHERE id = %s"
        return self._execute_update(query, (user_id,))

    def update_password(self, user_id: int, new_hashed_password: str) -> bool:
        """Хэрэглэгчийн нууц үгийг шинэчлэх"""
        query = "UPDATE users SET hashed_password = %s WHERE id = %s"
        return self._execute_update(query, (new_hashed_password, user_id))

    # --- Байгууллага (Admin) Үйлдлүүд ---

    def create_organization(self, name: str) -> Optional[int]:
        """Шинэ байгууллага үүсгэх"""
        query = "INSERT INTO organizations (name) VALUES (%s) RETURNING id;"
        return self._execute_returning_id(query, (name,))

    def get_all_organizations(self) -> List[Dict[str, Any]]:
        """Бүх байгууллагын жагсаалт авах"""
        query = "SELECT id, name, created_at FROM organizations ORDER BY name ASC;"
        return self._execute_fetch_all(query)

    # --- Камерын Үйлдлүүд ---

    def add_camera(self, name, url, cam_type, org_id) -> Optional[int]:
        """Байгууллагад камер холбох"""
        query = """
        INSERT INTO cameras (name, url, type, organization_id)
        VALUES (%s, %s, %s, %s) RETURNING id;
        """
        params = (name, url, cam_type, org_id)
        return self._execute_returning_id(query, params)

    def get_cameras_by_org(self, org_id: int) -> List[Dict[str, Any]]:
        """Тухайн байгууллагын камеруудыг авах"""
        query = "SELECT * FROM cameras WHERE organization_id = %s"
        return self._execute_fetch_all(query, (org_id,))

    # --- Өгөгдлийн сангийн Дотоод Үйлдлүүд (Execute Helpers) ---

    def _execute_returning_id(self, query, params) -> Optional[int]:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    result = cur.fetchone()
                    conn.commit()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Database Insert Error: {e}")
            return None

    def _execute_fetch_one(self, query, params=None) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Database Fetch Error: {e}")
            return None

    def _execute_fetch_all(self, query, params=None) -> List[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Database Fetch List Error: {e}")
            return []

    def _execute_update(self, query, params) -> bool:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Database Update Error: {e}")
            return False