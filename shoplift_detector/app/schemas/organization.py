from datetime import datetime

from pydantic import BaseModel


class OrganizationCreate(BaseModel):
    name: str


class OrganizationResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    store_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationList(BaseModel):
    items: list[OrganizationResponse]
    total: int
