from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CameraCreate(BaseModel):
    name: str
    url: str
    camera_type: str  # rtsp, mjpeg, usb, axis
    store_id: int
    is_ai_enabled: bool = True
    organization_id: Optional[int] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    camera_type: Optional[str] = None
    store_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_ai_enabled: Optional[bool] = None


class CameraResponse(BaseModel):
    id: int
    name: str
    url: str
    camera_type: str
    store_id: int
    store_name: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    is_active: bool
    is_ai_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CameraList(BaseModel):
    items: List[CameraResponse]
    total: int


class CameraStatus(BaseModel):
    camera_id: int
    name: str
    is_connected: bool
    fps: Optional[float] = None
    last_frame_at: Optional[datetime] = None
