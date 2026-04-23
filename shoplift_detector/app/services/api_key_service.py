"""Per-tenant API key lifecycle — generation + rotation.

Key format per DOC-05 §2.2:
    sk_live_<32-byte-urlsafe-base64>

Only the SHA-256 hex of the raw token is ever persisted. The raw
token is returned to the operator at creation/rotation time exactly
once — lost tokens require another rotation.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.repository.tenants import TenantRepository, hash_api_key

API_KEY_PREFIX = "sk_live_"

# Raw token entropy: 32 bytes → 43 base64url chars (no padding). Plus
# the 8-char prefix = 51 chars total.
API_KEY_ENTROPY_BYTES = 32

# Old key remains valid for 24h after rotation so deployed agents can
# roll over without downtime.
ROTATION_OVERLAP = timedelta(hours=24)


@dataclass(frozen=True)
class IssuedApiKey:
    """Returned to the caller of rotate/generate exactly once.

    `raw` is the string the operator must save — it's never
    retrievable again after this call.
    """

    raw: str
    hashed: str


def generate_api_key() -> IssuedApiKey:
    """Produce a fresh sk_live_* token + its hash. No I/O."""
    random_bytes = secrets.token_bytes(API_KEY_ENTROPY_BYTES)
    # urlsafe_b64encode + strip padding keeps the token a consistent
    # length (43 chars) and avoids `=` characters that would have to
    # be URL-escaped in agent config files.
    random_chunk = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")
    raw = f"{API_KEY_PREFIX}{random_chunk}"
    return IssuedApiKey(raw=raw, hashed=hash_api_key(raw))


async def rotate_api_key(
    repo: TenantRepository,
    tenant_id: str,
    *,
    now: datetime | None = None,
) -> IssuedApiKey:
    """Move the current key to the previous slot, install a new one.

    Returns the new raw token. The caller must surface it to the
    operator — after this function returns there's no way to recover
    the plaintext.

    Idempotency: calling rotate twice within the 24h window will
    overwrite the "previous" slot with the most recent pre-rotation
    key, which is the right behavior (no more than one rollback
    window at a time).
    """
    now = now or datetime.now(UTC)
    expires = now + ROTATION_OVERLAP
    new_key = generate_api_key()
    await repo.rotate_api_key(
        tenant_id=tenant_id,
        new_hash=new_key.hashed,
        previous_expires_at=expires,
        now=now,
    )
    return new_key
