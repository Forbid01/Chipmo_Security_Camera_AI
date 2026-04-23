"""Customer-portal tenant endpoints.

Scope: actions performed by the authenticated tenant on its own row —
nothing in this module crosses tenant boundaries. Admin transitions
(suspend / churn / grace) live in a separate admin router so they
can enforce a different dependency + audit trail (T1-10).
"""

from typing import Annotated

from app.core.tenant_auth import CurrentTenant
from app.db.repository.tenants import TenantRepository
from app.db.session import DB
from app.services.api_key_service import rotate_api_key
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class RotatedApiKeyResponse(BaseModel):
    """One-shot payload — the raw key is never retrievable again.

    The field ordering is intentional so a naive client that prints
    the whole object surfaces the token before the helper metadata.
    """

    raw_api_key: str
    previous_api_key_valid_until: str
    message: str = (
        "Энэ түлхүүрийг одоо л хадгалаарай. "
        "Sentry энэ plaintext-ийг дахин харуулахгүй. "
        "Хуучин түлхүүр 24 цагийн дотор хүчинтэй байна."
    )


@router.post(
    "/me/api-keys/rotate",
    response_model=RotatedApiKeyResponse,
    summary="Rotate the caller's API key (24h overlap)",
)
async def rotate_current_tenant_api_key(
    db: DB,
    tenant: CurrentTenant,
) -> RotatedApiKeyResponse:
    """Issue a new `sk_live_*` key and move the old one into the
    24-hour overlap slot. Both keys work until the overlap expires.

    The caller authenticates with the *current* key. After this call
    returns, the client must switch to the new key before the 24h
    window closes.
    """
    repo = TenantRepository(db)
    issued = await rotate_api_key(repo, tenant_id=str(tenant["tenant_id"]))

    # Re-read so we return the exact timestamp we persisted instead
    # of guessing from the service clock.
    refreshed = await repo.get_by_id(tenant["tenant_id"])
    expires_at = (
        refreshed.get("previous_api_key_expires_at") if refreshed else None
    )

    return RotatedApiKeyResponse(
        raw_api_key=issued.raw,
        previous_api_key_valid_until=(
            expires_at.isoformat() if expires_at else ""
        ),
    )
