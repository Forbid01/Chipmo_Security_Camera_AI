from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class StoreCreate(BaseModel):
    name: str
    address: Optional[str] = None
    organization_id: int
    alert_threshold: float = 80.0
    alert_cooldown: int = 15


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    alert_threshold: Optional[float] = None
    alert_cooldown: Optional[int] = None


class StoreResponse(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    organization_id: int
    organization_name: Optional[str] = None
    alert_threshold: float
    alert_cooldown: int
    camera_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreList(BaseModel):
    items: List[StoreResponse]
    total: int
