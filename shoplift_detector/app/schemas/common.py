from typing import Any

from pydantic import BaseModel


class APIResponse(BaseModel):
    status: str = "success"
    message: str | None = None
    data: Any | None = None


class APIError(BaseModel):
    status: str = "error"
    message: str
    detail: Any | None = None
    code: str | None = None


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
    ai_device: str | None = None


class StatsResponse(BaseModel):
    users: int = 0
    organizations: int = 0
    stores: int = 0
    cameras: int = 0
    alerts: int = 0
    active_cameras: int = 0
    today_alerts: int = 0
