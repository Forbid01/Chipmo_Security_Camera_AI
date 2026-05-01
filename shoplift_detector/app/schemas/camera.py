from datetime import datetime
from typing import Any

from pydantic import AnyUrl, BaseModel, Field, field_validator


class ShelfZone(BaseModel):
    """A shelf ROI polygon in normalized 0..1 coordinates.

    Stored per-camera so the AI service can detect hand-into-shelf
    interactions without depending on COCO object classes (which miss
    most real retail inventory).
    """

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    polygon: list[list[float]] = Field(min_length=3)

    @field_validator("polygon")
    @classmethod
    def _validate_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        for pt in v:
            if len(pt) != 2:
                raise ValueError("each polygon vertex must be [x, y]")
            x, y = pt
            if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
                raise ValueError("polygon coords must be normalized 0..1")
        return v


class ShelfZonesUpdate(BaseModel):
    zones: list[ShelfZone]


class CameraTestRequest(BaseModel):
    """Body for POST /cameras/test (T4-11).

    `url` is a full RTSP / HTTP URL (including credentials). We
    accept the raw string — Pydantic's URL parser rejects some valid
    RTSP shapes (non-standard ports, missing /path) so we validate
    shape only at the handler boundary."""

    url: str = Field(min_length=8, max_length=2048)
    manufacturer_id: str | None = Field(
        default=None,
        max_length=64,
        description="Vendor id from T4-10 catalog to key the failure hints on.",
    )


class CameraTestResponse(BaseModel):
    ok: bool
    message: str
    thumbnail_b64: str | None = None
    thumbnail_width: int | None = None
    thumbnail_height: int | None = None
    fps: float | None = None
    latency_ms: float | None = None
    credential_hints: list[dict[str, Any]] | None = None
    error_category: str | None = None  # "network" | "auth" | "encode" | None


class CameraCreate(BaseModel):
    name: str
    url: str
    camera_type: str  # rtsp, mjpeg, usb, axis
    store_id: int
    is_ai_enabled: bool = True
    organization_id: int | None = None
    # Optional sub-stream URL for AI inference (primary URL used for display).
    substream_url: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    camera_type: str | None = None
    store_id: int | None = None
    is_active: bool | None = None
    is_ai_enabled: bool | None = None
    substream_url: str | None = None


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
    substream_url: str | None = None
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


class ManufacturerItem(BaseModel):
    id: str
    display_name: str
    oui_prefixes: list[str]
    default_port: int


class CameraProbeRequest(BaseModel):
    """Body for POST /cameras/probe — generate + test candidate URLs."""

    manufacturer_id: str = Field(max_length=64)
    ip: str = Field(min_length=1, max_length=253)
    user: str = Field(default="admin", max_length=128)
    password: str = Field(default="", max_length=128)
    port: int | None = Field(default=None, ge=1, le=65535)


class CameraProbeResponse(BaseModel):
    ok: bool
    url: str | None = None          # first URL that succeeded
    message: str
    thumbnail_b64: str | None = None
    thumbnail_width: int | None = None
    thumbnail_height: int | None = None
    fps: float | None = None
    latency_ms: float | None = None
    credential_hints: list[dict[str, Any]] | None = None
    tried_urls: int = 0             # how many candidates were attempted
    error_category: str | None = None  # from the last failed attempt
