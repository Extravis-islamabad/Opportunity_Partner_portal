from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime


def normalise_email(value: str) -> str:
    """Emails are stored and compared lower-case.

    EmailStr only lower-cases the domain, so MARCUS.CHEN@x and marcus.chen@x
    were two different accounts, and somebody who typed their address with a
    capital could not sign in. Every write and every lookup goes through this
    (lookups also compare with func.lower, for rows stored before it).
    """
    return value.strip().lower()


class UserCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|partner|sales_rep)$")
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)
    company_id: Optional[int] = None

    _email = field_validator("email")(normalise_email)


class _ProfileFields(BaseModel):
    """The editable parts of an account, shared by self-service and admin edits.

    Only the fields actually sent are applied (callers use exclude_unset), so
    a request that names job_title alone must not touch phone or department.
    full_name is the one column that cannot be empty: an explicit null or a
    blank string used to reach the NOT NULL constraint and come back as a 500.
    The optional fields treat "" as "clear it", which is what an emptied form
    input sends.
    """

    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)

    @field_validator("full_name", mode="before")
    @classmethod
    def _full_name_required(cls, value):
        # Runs only when full_name was actually sent (defaults are not
        # validated), so leaving it out is still fine.
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Full name cannot be empty")
        return value.strip() if isinstance(value, str) else value

    @field_validator("job_title", "phone", "department", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class UserUpdateRequest(_ProfileFields):
    pass


class AdminUserUpdateRequest(_ProfileFields):
    # Not a plain column write: a change here is routed through the same
    # deactivate / reactivate rules as the dedicated endpoints (handover check,
    # suspension email, no "reactivating" a never-activated invite). See
    # partner_service.update_partner.
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

    _email = field_validator("email")(normalise_email)


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
    # The type of the user's company (partner / distributor / customer). A
    # distributor's staff have role "partner" — this is what lets the UI call
    # them distributors.
    company_type: Optional[str] = None
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
