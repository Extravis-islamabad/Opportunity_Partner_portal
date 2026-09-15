from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|partner|sales_rep)$")
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)
    company_id: Optional[int] = None


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)


class AdminUserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern="^(active|inactive)$")


class TeamMemberCreateRequest(BaseModel):
    """A partner adding one of their own company's employees.

    Unlike UserCreateRequest (an admin provisioning an account, who may not
    know an employee's designation or department yet), this is the partner
    filling in their own org chart, so contact, designation and department
    are all required. Role and company are implicit — always PARTNER, always
    the caller's own company — and the password is generated server-side
    rather than asked for.
    """

    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    contact: str = Field(..., min_length=1, max_length=50)
    designation: str = Field(..., min_length=1, max_length=255)
    department: str = Field(..., min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    status: str
    job_title: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    is_superadmin: bool = False
    # Channel-manager flags: a non-superadmin admin who is the channel
    # manager of one or more companies. Frontend uses this to render the
    # scoped sidebar and dashboard labels.
    is_channel_manager: bool = False
    managed_company_count: int = 0
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}




class HandoverRequest(BaseModel):
    """Who takes over a leaver's open work.

    One successor rather than one per kind: in practice everything a person
    holds is the same shape as the person (a partner's pipeline, an admin's
    book), and the service refuses a successor who cannot hold what is being
    moved rather than splitting it silently.
    """

    to_user_id: int
    notes: Optional[str] = Field(None, max_length=2000)
