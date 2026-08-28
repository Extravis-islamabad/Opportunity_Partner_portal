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
    # The person behind contact_email. Creating the company provisions a
    # portal account for them and mails an activation link, so this is the
    # name that greets them — falls back to the company name when omitted.
    contact_name: Optional[str] = Field(None, max_length=255)
    channel_manager_id: int
    # Required, with no default: classifying the company is a decision the
    # creator has to make, and it governs what that company's users can reach.
    company_type: str = Field(..., pattern=COMPANY_TYPE_PATTERN)
    # Optional reseller link. Only valid on a partner company, and only when it
    # points at a distributor — company_service.assert_valid_parent_distributor
    # is what enforces that; the schema can't, since it needs the other row.
    parent_distributor_id: Optional[int] = None


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
    # Superadmin-only too: the parent distributor decides who reads this
    # company's pipeline. Send it explicitly as null to unlink; omitting it
    # leaves the current link alone (the service uses exclude_unset).
    parent_distributor_id: Optional[int] = None


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
    # Set only on a partner company that resells through a distributor. Null
    # means the company reports directly to Extravis.
    parent_distributor_id: Optional[int] = None
    parent_distributor_name: Optional[str] = None
    partner_count: int = 0
    opportunity_count: int = 0
    # Only set on the create response: what happened to the contact's account
    # invite. One of "sent", "existing_user" (the address already had an
    # account, so nothing was created) or "failed" (the account exists but the
    # mail did not go out — re-send it from the user list). Read paths leave
    # it null; there is nothing to report about a company that already exists.
    contact_invite: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetailResponse(CompanyResponse):
    partners: List["PartnerAccountBrief"] = []
    # The companies sitting underneath this one. Only ever non-empty for a
    # distributor.
    resellers: List["ResellerBrief"] = []


class ResellerBrief(BaseModel):
    id: int
    name: str
    country: str
    status: str
    tier: Optional[str] = None

    model_config = {"from_attributes": True}


class PartnerAccountBrief(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    job_title: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


CompanyDetailResponse.model_rebuild()
