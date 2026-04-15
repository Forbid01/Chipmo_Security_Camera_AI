from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    phone_number: str | None = None
    full_name: str | None = None
    role: str
    organization_id: int | None = None
    organization_name: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRoleUpdate(BaseModel):
    role: str


class UserOrgUpdate(BaseModel):
    organization_id: int | None = None


class UserList(BaseModel):
    items: list[UserResponse]
    total: int


class ContactForm(BaseModel):
    name: str
    email: str
    subject: str
    message: str
