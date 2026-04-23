"""Per-request tenant resolution from the `Authorization` header.

Wires the Sentry DOC-05 §2.3 auth model into FastAPI:

    Authorization: Bearer sk_live_<32-byte-base64>

The raw token is never persisted — only its SHA-256 hex. The
dependency hashes the incoming token, looks up the matching tenant,
rejects anything that isn't `active`, and returns a dict the handlers
use in place of legacy `organization_id` / `CurrentUser`.
"""

from __future__ import annotations

from typing import Annotated, Any

from app.db.repository.tenants import TenantRepository, hash_api_key
from app.db.session import DB
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False so we can return a consistent 401 body instead of
# FastAPI's default "Not authenticated" string.
_bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="sk_live_*")

# Plan status that grants API access. Anything else → 401. Using a
# frozenset so accidental mutation somewhere else can't silently widen
# the allow list.
_ACCESS_STATUSES: frozenset[str] = frozenset({"active"})

# Token prefix the signup flow hands out. Tokens without the prefix
# are rejected up-front so we never even hash obvious noise.
API_KEY_PREFIX = "sk_live_"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="sentry"'},
    )


async def get_current_tenant(
    db: DB,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> dict[str, Any]:
    """Resolve the current tenant from the Bearer API key.

    Raises:
        401 if the header is missing, malformed, or doesn't match any
        tenant. Also 401 (not 403) if the tenant exists but isn't
        `active` — we deliberately don't leak status enumeration to a
        caller that presented a possibly-stolen key.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("API key required")

    raw = credentials.credentials.strip()
    if not raw.startswith(API_KEY_PREFIX):
        raise _unauthorized("Invalid API key format")

    api_key_hash = hash_api_key(raw)
    repo = TenantRepository(db)
    tenant = await repo.get_by_api_key_hash(api_key_hash)

    if tenant is None:
        raise _unauthorized("Invalid API key")

    if tenant.get("status") not in _ACCESS_STATUSES:
        # Same 401 body — don't disclose whether the key hit a
        # suspended vs churned vs pending tenant.
        raise _unauthorized("Invalid API key")

    return tenant


CurrentTenant = Annotated[dict[str, Any], Depends(get_current_tenant)]
