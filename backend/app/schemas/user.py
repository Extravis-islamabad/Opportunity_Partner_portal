from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|partner)$")
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    company_id: Optional[int] = None


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)


class AdminUserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    status: str
    job_title: Optional[str] = None
    phone: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    is_superadmin: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    status: str
    job_title: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
