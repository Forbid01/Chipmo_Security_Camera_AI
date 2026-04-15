from datetime import datetime

from pydantic import BaseModel


class CameraCreate(BaseModel):
    name: str
    url: str
    camera_type: str  # rtsp, mjpeg, usb, axis
    store_id: int
    is_ai_enabled: bool = True
    organization_id: int | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    camera_type: str | None = None
    store_id: int | None = None
    is_active: bool | None = None
    is_ai_enabled: bool | None = None


class CameraResponse(BaseModel):
    id: int
    name: str
    url: str
    camera_type: str
    store_id: int
    store_name: str | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    is_active: bool
    is_ai_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CameraList(BaseModel):
    items: list[CameraResponse]
    total: int


class CameraStatus(BaseModel):
    camera_id: int
    name: str
    is_connected: bool
    fps: float | None = None
    last_frame_at: datetime | None = None
