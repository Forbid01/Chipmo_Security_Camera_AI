from pydantic import BaseModel
from typing import Optional, Any


class APIResponse(BaseModel):
    status: str = "success"
    message: Optional[str] = None
    data: Optional[Any] = None


class APIError(BaseModel):
    status: str = "error"
    message: str
    detail: Optional[Any] = None
    code: Optional[str] = None


class PaginationParams(BaseModel):
    limit: int = 50
    offset: int = 0

    @property
    def skip(self) -> int:
        return self.offset


class HealthResponse(BaseModel):
    status: str
    version: str
    cameras: dict
    queues: dict
    database: str
    ai_device: Optional[str] = None


class StatsResponse(BaseModel):
    users: int = 0
    organizations: int = 0
    stores: int = 0
    cameras: int = 0
    alerts: int = 0
    active_cameras: int = 0
    today_alerts: int = 0
