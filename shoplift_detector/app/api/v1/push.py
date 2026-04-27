"""Push token register endpoint (T5-07).

Mobile + web clients POST their FCM / WebPush token here after login
so the escalation dispatcher knows where to fan out ORANGE/RED alerts.
All routes require a logged-in user (`CurrentUser`) — tokens are
scoped per user, not per tenant, because the same user might work
for multiple stores.
"""

from __future__ import annotations

from typing import Literal

from app.core.security import CurrentUser
from app.db.repository.push_tokens import PushTokenRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class PushTokenRegister(BaseModel):
    token: str = Field(min_length=8, max_length=4096)
    platform: Literal["ios", "android", "web"]


@router.post("/tokens", response_model=APIResponse)
async def register_push_token(
    data: PushTokenRegister,
    user: CurrentUser,
    db: DB,
):
    """Бүртгэгдсэн хэрэглэгчийн FCM token-ыг хадгалах. Идэмпотент —
    ижил token дахин ирвэл сүүлд харагдсан хугацааг шинэчилнэ."""
    repo = PushTokenRepository(db)
    try:
        token_id = await repo.register(
            user_id=user["user_id"],
            token=data.token,
            platform=data.platform,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if token_id is None:
        # Pre-migration schema — the table isn't there yet. Fail
        # cleanly so the mobile client can surface it rather than
        # silently "succeed".
        raise HTTPException(
            status_code=503,
            detail="push notifications are not yet configured on this server",
        )
    return APIResponse(
        message="Push token бүртгэгдлээ", data={"id": token_id}
    )


@router.delete("/tokens/{token}", response_model=APIResponse)
async def revoke_push_token(
    token: str,
    user: CurrentUser,
    db: DB,
):
    """Хэрэглэгч логоут эсвэл тохиргооноос утсыг нь хасах үед.

    Path-based — DELETE with a JSON body is an HTTP anti-pattern and
    a couple of proxies strip the body silently, so the token goes
    in the URL segment.
    """
    repo = PushTokenRepository(db)
    ok = await repo.unregister(token)
    if not ok:
        raise HTTPException(status_code=404, detail="Token олдсонгүй")
    return APIResponse(message="Push token устгагдлаа")
