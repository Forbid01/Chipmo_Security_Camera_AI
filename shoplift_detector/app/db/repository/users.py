import logging
import psycopg2.extras
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.db.base import BaseDB

logger = logging.getLogger(__name__)

class UserRepository(BaseDB):
    def __init__(self):
        super().__init__()

    async def _create_table(self):
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
                role VARCHAR(20) DEFAULT 'user',
                organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
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
                type VARCHAR(20),
                organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # 4. Индексүүд (Performance)
            "CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(organization_id);",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            "CREATE INDEX IF NOT EXISTS idx_cameras_org_id ON cameras(organization_id);",
        ]
        conn = self._get_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                for q in queries:
                    cur.execute(q)
                conn.commit()
        except Exception as e:
            logger.error(f"Table Creation Error: {e}")
        finally:
            self._return_connection(conn)

    # --- ХЭРЭГЛЭГЧИЙН ҮЙЛДЛҮҮД ---

    async def create(self, username, email, phone_number, hashed_password, full_name=None, organization_id=None, role='user') -> Optional[int]:
        query = """
        INSERT INTO users (username, email, phone_number, hashed_password, full_name, organization_id, role)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """
        params = (username, email, phone_number, hashed_password, full_name, organization_id, role)
        return await self._execute_returning_id(query, params)

    async def get_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        query = """
        SELECT u.*, o.name as organization_name
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        WHERE (u.username = %s OR u.email = %s) AND u.is_active = TRUE
        """
        return await self._execute_fetch_one(query, (identifier, identifier))

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM users WHERE email = %s AND is_active = TRUE"
        return await self._execute_fetch_one(query, (email,))

    # --- БАЙГУУЛЛАГА (ADMIN) ҮЙЛДЛҮҮД ---

    async def create_organization(self, name: str) -> Optional[int]:
        query = "INSERT INTO organizations (name) VALUES (%s) RETURNING id;"
        return await self._execute_returning_id(query, (name,))

    async def get_all_organizations(self) -> List[Dict[str, Any]]:
        query = "SELECT id, name, created_at FROM organizations ORDER BY created_at DESC;"
        return await self._execute_fetch_all(query)

    async def delete_organization(self, org_id: int) -> bool:
        """Байгууллага устгах (Камерууд нь CASCADE-ээр хамт устгагдана)"""
        query = "DELETE FROM organizations WHERE id = %s"
        return await self._execute_update(query, (org_id,))

    # --- КАМЕРЫН ҮЙЛДЛҮҮД ---

    async def add_camera(self, name, url, cam_type, org_id) -> Optional[int]:
        query = """
        INSERT INTO cameras (name, url, type, organization_id)
        VALUES (%s, %s, %s, %s) RETURNING id;
        """
        params = (name, url, cam_type, org_id)
        return await self._execute_returning_id(query, params)

    async def get_all_cameras(self) -> List[Dict[str, Any]]:
        """Бүх камерыг байгууллагын нэртэй нь хамт авах (Admin Dashboard-д зориулсан)"""
        query = """
        SELECT c.*, o.name as organization_name 
        FROM cameras c 
        LEFT JOIN organizations o ON c.organization_id = o.id 
        ORDER BY c.created_at DESC;
        """
        return await self._execute_fetch_all(query)

    async def delete_camera(self, cam_id: int) -> bool:
        query = "DELETE FROM cameras WHERE id = %s"
        return await self._execute_update(query, (cam_id,))

    # --- НУУЦ ҮГ СЭРГЭЭХ ---

    async def update_recovery_data(self, user_id: int, code: str, expiry: datetime) -> bool:
        query = "UPDATE users SET recovery_code = %s, recovery_code_expires = %s WHERE id = %s"
        return await self._execute_update(query, (code, expiry, user_id))

    async def clear_recovery_data(self, user_id: int) -> bool:
        query = "UPDATE users SET recovery_code = NULL, recovery_code_expires = NULL WHERE id = %s"
        return await self._execute_update(query, (user_id,))

    async def update_password(self, user_id: int, new_hashed_password: str) -> bool:
        query = "UPDATE users SET hashed_password = %s WHERE id = %s"
        return await self._execute_update(query, (new_hashed_password, user_id))

    # --- ӨГӨГДЛИЙН САНГИЙН ТУСЛАХ ФУНКЦҮҮД (HELPERS) ---

    async def _execute_returning_id(self, query, params) -> Optional[int]:
        conn = self._get_connection()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Database Insert Error: {e}")
            return None
        finally:
            self._return_connection(conn)

    async def _execute_fetch_one(self, query, params=None) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchone()
        except Exception as e:
            logger.error(f"Database Fetch Error: {e}")
            return None
        finally:
            self._return_connection(conn)

    async def _execute_fetch_all(self, query, params=None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        if not conn:
            return []
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Database Fetch List Error: {e}")
            return []
        finally:
            self._return_connection(conn)

    async def _execute_update(self, query, params) -> bool:
        conn = self._get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Database Update Error: {e}")
            return False
        finally:
            self._return_connection(conn)