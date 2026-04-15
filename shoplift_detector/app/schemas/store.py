from datetime import datetime

from pydantic import BaseModel


class StoreCreate(BaseModel):
    name: str
    address: str | None = None
    organization_id: int
    alert_threshold: float = 80.0
    alert_cooldown: int = 15
    telegram_chat_id: str | None = None


class StoreUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    alert_threshold: float | None = None
    alert_cooldown: int | None = None
    telegram_chat_id: str | None = None


class StoreResponse(BaseModel):
    id: int
    name: str
    address: str | None = None
    organization_id: int
    organization_name: str | None = None
    alert_threshold: float
    alert_cooldown: int
    telegram_chat_id: str | None = None
    camera_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreList(BaseModel):
    items: list[StoreResponse]
    total: int
