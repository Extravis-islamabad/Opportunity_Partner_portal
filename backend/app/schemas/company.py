from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


COMPANY_TYPE_PATTERN = "^(customer|distributor|partner)$"


class CompanyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(..., min_length=1, max_length=100)
    region: str = Field(..., min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    industry: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr
    channel_manager_id: int
    # Required, with no default: classifying the company is a decision the
    # creator has to make, and it governs what that company's users can reach.
    company_type: str = Field(..., pattern=COMPANY_TYPE_PATTERN)


class CompanyUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    region: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    industry: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_email: Optional[EmailStr] = None
    channel_manager_id: Optional[int] = None
    # Superadmin-only — enforced in the endpoint, same as channel_manager_id.
    company_type: Optional[str] = Field(None, pattern=COMPANY_TYPE_PATTERN)


class CompanyResponse(BaseModel):
    id: int
    name: str
    country: str
    region: str
    city: str
    industry: str
    contact_email: str
    status: str
    company_type: str
    # Null for a customer company — partner tier has no meaning there. See
    # company_service.tier_for.
    tier: Optional[str] = None
    channel_manager_id: int
    channel_manager_name: Optional[str] = None
    partner_count: int = 0
    opportunity_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetailResponse(CompanyResponse):
    partners: List["PartnerAccountBrief"] = []


class PartnerAccountBrief(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    job_title: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


CompanyDetailResponse.model_rebuild()
