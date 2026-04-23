"""OTP lifecycle — generate, hash, verify (T2-02, T2-04).

A 6-digit code is generated with `secrets.randbelow(10**6)` so the
distribution is uniform. Only its SHA-256 hex is stored; the raw
code is delivered out-of-band (email/SMS). Verification hashes the
user-supplied code and compares with `hmac.compare_digest` for
constant-time equality.

Per the spec (T2-02):
- 6-digit numeric code
- 15-minute expiry
- 3 attempts per code, then the row is locked out

Rate limiting of OTP creation (1 per minute per email) is enforced
by the handler chain via the existing `TenantRateLimiter`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 3


def generate_code() -> str:
    """Return a zero-padded 6-digit string."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedOtp:
    """Returned to the signup/resend handler — the raw code goes to
    the delivery channel, the id is stored for client correlation."""

    id: UUID
    raw_code: str
    expires_at: datetime
    channel: str
    destination: str


class OtpRepository:
    """Data access for otp_challenges."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        tenant_id: UUID | str,
        channel: str,
        destination: str,
        code_hash: str,
        expires_at: datetime,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> dict[str, Any]:
        query = text("""
            INSERT INTO otp_challenges (
                tenant_id, channel, destination,
                code_hash, expires_at, max_attempts
            )
            VALUES (
                CAST(:tenant_id AS UUID),
                :channel, :destination,
                :code_hash, :expires_at, :max_attempts
            )
            RETURNING id, tenant_id, channel, destination,
                      expires_at, max_attempts, attempts,
                      used_at, created_at
        """)
        result = await self.db.execute(
            query,
            {
                "tenant_id": str(tenant_id),
                "channel": channel,
                "destination": destination,
                "code_hash": code_hash,
                "expires_at": expires_at,
                "max_attempts": max_attempts,
            },
        )
        await self.db.commit()
        return dict(result.mappings().fetchone())

    async def get_latest_unused(
        self,
        *,
        tenant_id: UUID | str,
        channel: str,
    ) -> dict[str, Any] | None:
        query = text("""
            SELECT id, tenant_id, channel, destination,
                   code_hash, expires_at, max_attempts, attempts,
                   used_at, created_at
              FROM otp_challenges
             WHERE tenant_id = CAST(:tenant_id AS UUID)
               AND channel = :channel
               AND used_at IS NULL
          ORDER BY created_at DESC
             LIMIT 1
        """)
        result = await self.db.execute(
            query, {"tenant_id": str(tenant_id), "channel": channel}
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None

    async def increment_attempts(self, otp_id: UUID | str) -> int:
        query = text("""
            UPDATE otp_challenges
               SET attempts = attempts + 1
             WHERE id = CAST(:id AS UUID)
         RETURNING attempts, max_attempts
        """)
        result = await self.db.execute(query, {"id": str(otp_id)})
        row = result.mappings().fetchone()
        await self.db.commit()
        return int(row["attempts"]) if row else 0

    async def mark_used(self, otp_id: UUID | str) -> None:
        query = text("""
            UPDATE otp_challenges
               SET used_at = now()
             WHERE id = CAST(:id AS UUID)
        """)
        await self.db.execute(query, {"id": str(otp_id)})
        await self.db.commit()


class OtpVerificationError(ValueError):
    """Base for verify() failures — handler maps to 400."""


class OtpExpired(OtpVerificationError):
    pass


class OtpExhausted(OtpVerificationError):
    """The user has burned all their attempts on this code."""


class OtpCodeMismatch(OtpVerificationError):
    pass


class OtpNotFound(OtpVerificationError):
    pass


async def issue_otp(
    repo: OtpRepository,
    *,
    tenant_id: UUID | str,
    channel: str,
    destination: str,
    now: datetime | None = None,
) -> IssuedOtp:
    """Generate a fresh code, persist its hash, return the raw so the
    caller can dispatch it via email / SMS."""
    now = now or datetime.now(UTC)
    expires = now + CODE_TTL
    code = generate_code()
    row = await repo.create(
        tenant_id=tenant_id,
        channel=channel,
        destination=destination,
        code_hash=hash_code(code),
        expires_at=expires,
    )
    return IssuedOtp(
        id=row["id"],
        raw_code=code,
        expires_at=row["expires_at"],
        channel=channel,
        destination=destination,
    )


async def verify_otp(
    repo: OtpRepository,
    *,
    tenant_id: UUID | str,
    channel: str,
    submitted_code: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the row on success, raise on failure.

    Contract:
    - OtpNotFound — no unused row for this tenant/channel.
    - OtpExpired — row's expiry has passed.
    - OtpExhausted — attempts already reached max.
    - OtpCodeMismatch — code wrong; attempts counter incremented.
    """
    now = now or datetime.now(UTC)
    row = await repo.get_latest_unused(tenant_id=tenant_id, channel=channel)
    if row is None:
        raise OtpNotFound("no active verification challenge")

    if row["expires_at"] <= now:
        raise OtpExpired("verification code has expired")

    if row["attempts"] >= row["max_attempts"]:
        raise OtpExhausted("too many failed attempts")

    supplied_hash = hash_code(submitted_code.strip())
    if not hmac.compare_digest(supplied_hash, row["code_hash"]):
        attempts_after = await repo.increment_attempts(row["id"])
        if attempts_after >= row["max_attempts"]:
            raise OtpExhausted("too many failed attempts")
        raise OtpCodeMismatch("verification code is incorrect")

    await repo.mark_used(row["id"])
    return row
