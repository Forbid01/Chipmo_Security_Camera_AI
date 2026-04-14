from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class OrganizationCreate(BaseModel):
    name: str


class OrganizationResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    store_count: int = 0

    model_config = {"from_attributes": True}


class OrganizationList(BaseModel):
    items: List[OrganizationResponse]
    total: int
