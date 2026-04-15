import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, username, email, phone_number, hashed_password,
                     full_name=None, organization_id=None, role='user') -> int | None:
        query = text("""
            INSERT INTO users (username, email, phone_number, hashed_password, full_name, organization_id, role)
            VALUES (:username, :email, :phone_number, :hashed_password, :full_name, :organization_id, :role)
            RETURNING id
        """)
        result = await self.db.execute(query, {
            "username": username, "email": email, "phone_number": phone_number,
            "hashed_password": hashed_password, "full_name": full_name,
            "organization_id": organization_id, "role": role,
        })
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_by_identifier(self, identifier: str) -> dict[str, Any] | None:
        query = text("""
            SELECT u.*, o.name as organization_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            WHERE (u.username = :ident OR u.email = :ident) AND u.is_active = TRUE
        """)
        result = await self.db.execute(query, {"ident": identifier})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        query = text("SELECT * FROM users WHERE email = :email AND is_active = TRUE")
        result = await self.db.execute(query, {"email": email})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        query = text("SELECT * FROM users WHERE id = :id")
        result = await self.db.execute(query, {"id": user_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_all_users(self) -> list[dict[str, Any]]:
        query = text("""
            SELECT u.id, u.username, u.email, u.full_name, u.role,
                   u.organization_id, o.name as organization_name, u.is_active, u.created_at
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            ORDER BY u.created_at DESC
        """)
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def update_user_role(self, user_id: int, role: str) -> bool:
        query = text("UPDATE users SET role = :role WHERE id = :id")
        result = await self.db.execute(query, {"role": role, "id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    async def update_user_organization(self, user_id: int, organization_id: int = None) -> bool:
        query = text("UPDATE users SET organization_id = :org_id WHERE id = :id")
        result = await self.db.execute(query, {"org_id": organization_id, "id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    async def deactivate_user(self, user_id: int) -> bool:
        query = text("UPDATE users SET is_active = FALSE WHERE id = :id")
        result = await self.db.execute(query, {"id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    async def update_recovery_data(self, user_id: int, code: str, expiry: datetime) -> bool:
        query = text("UPDATE users SET recovery_code = :code, recovery_code_expires = :expiry WHERE id = :id")
        result = await self.db.execute(query, {"code": code, "expiry": expiry, "id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    async def clear_recovery_data(self, user_id: int) -> bool:
        query = text("UPDATE users SET recovery_code = NULL, recovery_code_expires = NULL WHERE id = :id")
        result = await self.db.execute(query, {"id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    async def update_password(self, user_id: int, new_hashed_password: str) -> bool:
        query = text("UPDATE users SET hashed_password = :pwd WHERE id = :id")
        result = await self.db.execute(query, {"pwd": new_hashed_password, "id": user_id})
        await self.db.commit()
        return result.rowcount > 0

    # --- Organizations ---

    async def create_organization(self, name: str) -> int | None:
        query = text("INSERT INTO organizations (name) VALUES (:name) RETURNING id")
        result = await self.db.execute(query, {"name": name})
        await self.db.commit()
        row = result.fetchone()
        return row[0] if row else None

    async def get_or_create_organization(self, name: str) -> int | None:
        existing = await self.db.execute(
            text("SELECT id FROM organizations WHERE name = :name LIMIT 1"),
            {"name": name},
        )
        row = existing.fetchone()
        if row:
            return row[0]
        return await self.create_organization(name)

    async def get_all_organizations(self) -> list[dict[str, Any]]:
        query = text("SELECT id, name, created_at FROM organizations ORDER BY created_at DESC")
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def delete_organization(self, org_id: int) -> bool:
        query = text("DELETE FROM organizations WHERE id = :id")
        result = await self.db.execute(query, {"id": org_id})
        await self.db.commit()
        return result.rowcount > 0

    # --- Cameras (legacy compat) ---

    async def get_all_cameras(self) -> list[dict[str, Any]]:
        query = text("""
            SELECT c.*, o.name as organization_name, s.name as store_name
            FROM cameras c
            LEFT JOIN organizations o ON c.organization_id = o.id
            LEFT JOIN stores s ON c.store_id = s.id
            ORDER BY c.created_at DESC
        """)
        result = await self.db.execute(query)
        return [dict(row) for row in result.mappings().fetchall()]

    async def get_stats(self) -> dict[str, Any]:
        query = text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE is_active = TRUE) as users,
                (SELECT COUNT(*) FROM organizations) as organizations,
                (SELECT COUNT(*) FROM cameras) as cameras,
                (SELECT COUNT(*) FROM alerts) as alerts
        """)
        result = await self.db.execute(query)
        row = result.mappings().fetchone()
        return dict(row) if row else {"users": 0, "organizations": 0, "cameras": 0, "alerts": 0}
