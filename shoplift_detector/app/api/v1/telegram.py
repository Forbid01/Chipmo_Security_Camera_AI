"""Telegram мэдэгдлийн тохиргооны endpoint-ууд."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.db.repository.stores import StoreRepository
from app.schemas.common import APIResponse

router = APIRouter()


class TelegramSetup(BaseModel):
    store_id: int
    chat_id: str


@router.post("/setup", response_model=APIResponse)
async def setup_telegram(
    data: TelegramSetup,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Дэлгүүрт Telegram chat_id бүртгэх."""
    store_repo = StoreRepository(db)
    store = await store_repo.get_by_id(data.store_id)

    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")

    # Эрх шалгах
    if user.get("role") != "super_admin" and store.get("organization_id") != user.get("org_id"):
        raise HTTPException(status_code=403, detail="Энэ дэлгүүрт хандах эрхгүй")

    from app.schemas.store import StoreUpdate
    success = await store_repo.update(data.store_id, StoreUpdate(telegram_chat_id=data.chat_id))

    if not success:
        raise HTTPException(status_code=400, detail="Хадгалах боломжгүй")

    return APIResponse(message="Telegram холбогдлоо", data={"store_id": data.store_id, "chat_id": data.chat_id})


@router.post("/test", response_model=APIResponse)
async def test_telegram(
    data: TelegramSetup,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Тест мэдэгдэл илгээх."""
    store_repo = StoreRepository(db)
    store = await store_repo.get_by_id(data.store_id)

    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")

    if user.get("role") != "super_admin" and store.get("organization_id") != user.get("org_id"):
        raise HTTPException(status_code=403, detail="Энэ дэлгүүрт хандах эрхгүй")

    from app.services.telegram_notifier import telegram_notifier
    if not telegram_notifier.is_configured:
        raise HTTPException(status_code=400, detail="Telegram bot тохируулаагүй байна. TELEGRAM_TOKEN .env-д нэмнэ үү.")

    success = await telegram_notifier.send_test(data.chat_id)
    if not success:
        raise HTTPException(status_code=400, detail="Мэдэгдэл илгээж чадсангүй. Chat ID шалгана уу.")

    # Амжилттай бол chat_id хадгалах
    from app.schemas.store import StoreUpdate
    await store_repo.update(data.store_id, StoreUpdate(telegram_chat_id=data.chat_id))

    return APIResponse(message="Тест мэдэгдэл илгээгдлээ!")


@router.delete("/{store_id}", response_model=APIResponse)
async def remove_telegram(
    store_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Дэлгүүрийн Telegram мэдэгдлийг унтраах."""
    store_repo = StoreRepository(db)
    store = await store_repo.get_by_id(store_id)

    if not store:
        raise HTTPException(status_code=404, detail="Дэлгүүр олдсонгүй")

    if user.get("role") != "super_admin" and store.get("organization_id") != user.get("org_id"):
        raise HTTPException(status_code=403, detail="Энэ дэлгүүрт хандах эрхгүй")

    from app.schemas.store import StoreUpdate
    await store_repo.update(store_id, StoreUpdate(telegram_chat_id=None))

    return APIResponse(message="Telegram мэдэгдэл унтраагдлаа")
