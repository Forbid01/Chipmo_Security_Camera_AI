"""Telegram мэдэгдлийн тохиргооны endpoint-ууд.

All handlers route through `require_store_access` so tenant scoping
and 404-on-cross-tenant are centralized (T02-21 / closes H-H12).
"""

from typing import Annotated

from app.core.security import CurrentUser
from app.core.tenancy import require_store_access
from app.db.repository.stores import StoreRepository
from app.db.session import DB
from app.schemas.common import APIResponse
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()


class TelegramSetup(BaseModel):
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
