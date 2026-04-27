"""Telegram мэдэгдлийн тохиргооны endpoint-ууд.

All handlers route through `require_store_access` so tenant scoping
and 404-on-cross-tenant are centralized (T02-21 / closes H-H12).

T5-03 adds an unauthenticated `/webhook` endpoint that receives
updates from the Telegram Bot API. T5-04 adds subscribe/list/
unsubscribe endpoints on top of the new `store_telegram_subscribers`
table.
"""

import os
from typing import Annotated, Literal

from app.core.security import CurrentUser
from app.core.tenancy import require_store_access
from app.db.repository.stores import StoreRepository
from app.db.repository.telegram_subscribers import TelegramSubscriberRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from app.services.telegram_bot import handle_update
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter()


class TelegramSetup(BaseModel):
    store_id: int
    chat_id: str


class TelegramSubscriberCreate(BaseModel):
    store_id: int
    chat_id: str
    role: Literal["owner", "manager", "staff"] = "manager"


class TelegramSubscriberRemove(BaseModel):
    store_id: int
    chat_id: str


async def _require_store_from_payload(
    data: TelegramSetup,
    user: CurrentUser,
    db: DB,
) -> dict:
    return await require_store_access(data.store_id, user, db)


@router.post("/setup", response_model=APIResponse)
async def setup_telegram(
    data: TelegramSetup,
    db: DB,
    store: Annotated[dict, Depends(_require_store_from_payload)],
):
    """Дэлгүүрт Telegram chat_id бүртгэх."""
    from app.schemas.store import StoreUpdate

    store_repo = StoreRepository(db)
    success = await store_repo.update(
        data.store_id, StoreUpdate(telegram_chat_id=data.chat_id)
    )
    if not success:
        raise HTTPException(status_code=400, detail="Хадгалах боломжгүй")

    return APIResponse(
        message="Telegram холбогдлоо",
        data={"store_id": data.store_id, "chat_id": data.chat_id},
    )


@router.post("/test", response_model=APIResponse)
async def test_telegram(
    data: TelegramSetup,
    db: DB,
    store: Annotated[dict, Depends(_require_store_from_payload)],
):
    """Тест мэдэгдэл илгээх."""
    from app.schemas.store import StoreUpdate
    from app.services.telegram_notifier import telegram_notifier

    if not telegram_notifier.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Telegram bot тохируулаагүй байна. TELEGRAM_TOKEN .env-д нэмнэ үү.",
        )

    success = await telegram_notifier.send_test(data.chat_id)
    if not success:
        raise HTTPException(
            status_code=400, detail="Мэдэгдэл илгээж чадсангүй. Chat ID шалгана уу."
        )

    store_repo = StoreRepository(db)
    await store_repo.update(
        data.store_id, StoreUpdate(telegram_chat_id=data.chat_id)
    )

    return APIResponse(message="Тест мэдэгдэл илгээгдлээ!")


@router.delete("/{store_id}", response_model=APIResponse)
async def remove_telegram(
    store_id: int,
    db: DB,
    store: Annotated[dict, Depends(require_store_access)],
):
    """Дэлгүүрийн Telegram мэдэгдлийг унтраах."""
    from app.schemas.store import StoreUpdate

    store_repo = StoreRepository(db)
    await store_repo.update(store_id, StoreUpdate(telegram_chat_id=None))
    return APIResponse(message="Telegram мэдэгдэл унтраагдлаа")


# ---------------------------------------------------------------------------
# T5-04 — multiple subscribers per store
# ---------------------------------------------------------------------------

async def _require_subscriber_store(
    data: TelegramSubscriberCreate | TelegramSubscriberRemove,
    user: CurrentUser,
    db: DB,
) -> dict:
    return await require_store_access(data.store_id, user, db)


@router.get("/subscribers/{store_id}")
async def list_subscribers(
    store_id: int,
    db: DB,
    store: Annotated[dict, Depends(require_store_access)],
):
    """Дэлгүүрийн бүх Telegram subscriber-уудыг жагсаах."""
    repo = TelegramSubscriberRepository(db)
    rows = await repo.list_for_store(store_id)
    return {"store_id": store_id, "subscribers": rows}


@router.post("/subscribers", response_model=APIResponse)
async def add_subscriber(
    data: TelegramSubscriberCreate,
    db: DB,
    store: Annotated[dict, Depends(_require_subscriber_store)],
):
    """Дэлгүүрт Telegram subscriber нэмэх (эсвэл role-ыг шинэчлэх)."""
    repo = TelegramSubscriberRepository(db)
    try:
        sub_id = await repo.add(
            store_id=data.store_id,
            chat_id=data.chat_id,
            role=data.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(
        message="Subscriber бүртгэгдлээ",
        data={"id": sub_id, "role": data.role},
    )


@router.delete("/subscribers", response_model=APIResponse)
async def remove_subscriber(
    data: TelegramSubscriberRemove,
    db: DB,
    store: Annotated[dict, Depends(_require_subscriber_store)],
):
    """Subscriber устгах."""
    repo = TelegramSubscriberRepository(db)
    ok = await repo.remove(store_id=data.store_id, chat_id=data.chat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Subscriber олдсонгүй")
    return APIResponse(message="Subscriber устгагдлаа")


# ---------------------------------------------------------------------------
# T5-03 — bot webhook
# ---------------------------------------------------------------------------

@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Telegram-ээс ирэх update-уудыг хүлээн авч bot command-уудыг
    биелүүлнэ.

    Telegram сервертэй `setWebhook` хийх үед `secret_token`-ыг
    тохируулдаг бөгөөд тэр нь `X-Telegram-Bot-Api-Secret-Token` гэсэн
    header-ээр эргэж ирдэг. Бид `TELEGRAM_WEBHOOK_SECRET` env var-тай
    тулгаж тогтоодог — тохирохгүй бол 401 буцаах нь spoofing-аас
    хамгаална.

    Webhook-ийг мэдээжгээр HTTPS дээр тохируулсан байх ёстой (Telegram
    нь HTTP webhook-ийг зөвшөөрдөггүй).
    """
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if expected_secret:
        if x_telegram_bot_api_secret_token != expected_secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid webhook secret",
            )

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="webhook body must be JSON",
        ) from None

    await handle_update(update)
    # 204 No Content — Telegram only cares that we accepted the update;
    # any body is ignored and an empty response is cheaper.
    return None
