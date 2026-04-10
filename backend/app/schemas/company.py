from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class CompanyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(..., min_length=1, max_length=100)
    region: str = Field(..., min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    industry: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr
    channel_manager_id: int


class CompanyUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    region: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    industry: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_email: Optional[EmailStr] = None
    channel_manager_id: Optional[int] = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    country: str
    region: str
    city: str
    industry: str
    contact_email: str
    status: str
    tier: str
    channel_manager_id: int
    channel_manager_name: Optional[str] = None
    partner_count: int = 0
    opportunity_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    id: int
    name: str
    country: str
    region: str
    city: str
    industry: str
    status: str
    tier: str
    channel_manager_id: int
    channel_manager_name: Optional[str] = None
    partner_count: int = 0
    created_at: datetime

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
