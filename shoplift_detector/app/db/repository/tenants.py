"""Data access for tenants table.

Read-path + rotation. Tenant rows are created by the signup flow
(T2-01) and mutated by the billing / lifecycle services (T1-10, T3).
"""

import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def hash_api_key(raw_api_key: str) -> str:
    """SHA-256 hex of the raw `sk_live_*` token.

    The raw token is never persisted. This function must match the
    one used at generation time so lookup-by-hash works.
    """
    return hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()


class TenantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_api_key_hash(self, api_key_hash: str) -> dict[str, Any] | None:
        """Fetch the tenant row whose api_key_hash matches, or None.

        Also matches `previous_api_key_hash` when it is set and hasn't
        expired — this is the 24h rotation overlap from T1-06 so old
        deployed agents keep working until they upgrade.
        """
        query = text("""
            SELECT tenant_id,
                   legal_name,
                   display_name,
                   email,
                   phone,
                   status,
                   plan,
                   created_at,
                   trial_ends_at,
                   current_period_end,
                   payment_method_id,
                   resource_quota,
                   previous_api_key_hash,
                   previous_api_key_expires_at
            FROM tenants
            WHERE api_key_hash = :api_key_hash
               OR (
                   previous_api_key_hash = :api_key_hash
                   AND previous_api_key_expires_at IS NOT NULL
                   AND previous_api_key_expires_at > now()
               )
            LIMIT 1
        """)
        result = await self.db.execute(query, {"api_key_hash": api_key_hash})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        query = text("""
            SELECT tenant_id,
                   legal_name,
                   display_name,
                   email,
                   phone,
                   status,
                   plan,
                   onboarding_step,
                   email_verified_at,
                   phone_verified_at,
                   created_at,
                   trial_ends_at,
                   current_period_end,
                   payment_method_id,
                   resource_quota
            FROM tenants
            WHERE lower(email) = lower(:email)
            LIMIT 1
        """)
        result = await self.db.execute(query, {"email": email})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def create_pending(
        self,
        *,
        email: str,
        phone: str | None,
        legal_name: str,
        display_name: str,
        api_key_hash: str,
        resource_quota: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a tenant row in the `pending` lifecycle /
        `pending_email` onboarding state. Used by `POST /signup`.

        Raises IntegrityError if the email is already taken — handler
        translates to 409 without leaking whether the duplicate
        existed before.
        """
        import json

        query = text("""
            INSERT INTO tenants (
                legal_name, display_name, email, phone,
                status, plan, onboarding_step,
                api_key_hash, resource_quota
            )
            VALUES (
                :legal_name, :display_name, :email, :phone,
                'pending', 'trial', 'pending_email',
                :api_key_hash, CAST(:resource_quota AS JSONB)
            )
            RETURNING tenant_id, legal_name, display_name, email,
                      phone, status, plan, onboarding_step,
                      resource_quota, created_at
        """)
        result = await self.db.execute(
            query,
            {
                "legal_name": legal_name,
                "display_name": display_name,
                "email": email,
                "phone": phone,
                "api_key_hash": api_key_hash,
                "resource_quota": json.dumps(resource_quota),
            },
        )
        await self.db.commit()
        return dict(result.mappings().fetchone())

    async def mark_email_verified(
        self,
        tenant_id: UUID | str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Flip email_verified_at and advance onboarding_step to
        pending_plan. Idempotent — re-running with an already-verified
        tenant is a no-op."""
        query = text("""
            UPDATE tenants
               SET email_verified_at = COALESCE(:now, now()),
                   onboarding_step = CASE
                       WHEN onboarding_step = 'pending_email'
                           THEN 'pending_plan'
                       ELSE onboarding_step
                   END
             WHERE tenant_id = CAST(:tenant_id AS UUID)
        """)
        await self.db.execute(
            query, {"tenant_id": str(tenant_id), "now": now}
        )
        await self.db.commit()

    async def set_onboarding_step(
        self,
        tenant_id: UUID | str,
        step: str,
    ) -> None:
        query = text("""
            UPDATE tenants
               SET onboarding_step = :step
             WHERE tenant_id = CAST(:tenant_id AS UUID)
        """)
        await self.db.execute(
            query, {"tenant_id": str(tenant_id), "step": step}
        )
        await self.db.commit()

    async def get_tenant_id_for_organization(
        self, organization_id: int | None
    ) -> str | None:
        """Resolve a legacy organization_id to its tenant UUID via the
        T1-02 map table. Returns a canonical string form or None when
        the org has no tenant row yet (pre-migration shells).
        """
        if organization_id is None:
            return None
        query = text("""
            SELECT tenant_id
              FROM organization_tenant_map
             WHERE organization_id = :organization_id
             LIMIT 1
        """)
        result = await self.db.execute(
            query, {"organization_id": organization_id}
        )
        row = result.scalar_one_or_none()
        return str(row) if row is not None else None

    async def get_by_id(self, tenant_id: UUID | str) -> dict[str, Any] | None:
        query = text("""
            SELECT tenant_id,
                   legal_name,
                   display_name,
                   email,
                   phone,
                   status,
                   plan,
                   created_at,
                   trial_ends_at,
                   current_period_end,
                   payment_method_id,
                   resource_quota
            FROM tenants
            WHERE tenant_id = CAST(:tenant_id AS UUID)
            LIMIT 1
        """)
        result = await self.db.execute(query, {"tenant_id": str(tenant_id)})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def rotate_api_key(
        self,
        *,
        tenant_id: UUID | str,
        new_hash: str,
        previous_expires_at: datetime,
        now: datetime,
    ) -> None:
        """Atomic rotation — move current hash to previous slot,
        install the new one, set the 24h overlap window.

        The new key's uniqueness is enforced by the UNIQUE constraint
        on `api_key_hash`; `IntegrityError` should propagate so the
        caller retries with a freshly generated token.
        """
        query = text("""
            UPDATE tenants
               SET previous_api_key_hash = api_key_hash,
                   previous_api_key_expires_at = :previous_expires_at,
                   api_key_hash = :new_hash
             WHERE tenant_id = CAST(:tenant_id AS UUID)
        """)
        await self.db.execute(
            query,
            {
                "tenant_id": str(tenant_id),
                "new_hash": new_hash,
                "previous_expires_at": previous_expires_at,
            },
        )
        await self.db.commit()

    async def clear_expired_rotation_keys(self, now: datetime | None = None) -> int:
        """Sweeper cron target — null out previous_api_key_hash rows
        whose overlap window has elapsed. Returns rowcount."""
        query = text("""
            UPDATE tenants
               SET previous_api_key_hash = NULL,
                   previous_api_key_expires_at = NULL
             WHERE previous_api_key_hash IS NOT NULL
               AND previous_api_key_expires_at IS NOT NULL
               AND previous_api_key_expires_at <= COALESCE(:now, now())
        """)
        result = await self.db.execute(query, {"now": now})
        await self.db.commit()
        return result.rowcount
