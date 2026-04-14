from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: str


class UserOrgUpdate(BaseModel):
    organization_id: Optional[int] = None


class UserList(BaseModel):
    items: List[UserResponse]
    total: int


class ContactForm(BaseModel):
    name: str
    email: str
    subject: str
    message: str
