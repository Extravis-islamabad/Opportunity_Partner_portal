from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


class OpportunityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    customer_name: str = Field(..., min_length=1, max_length=200)
    region: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    worth: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)
    closing_date: date
    requirements: str = Field(..., min_length=1)
    status: Optional[str] = Field("draft", pattern="^(draft|pending_review)$")


class OpportunityUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    customer_name: Optional[str] = Field(None, min_length=1, max_length=200)
    region: Optional[str] = Field(None, min_length=1, max_length=100)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    worth: Optional[Decimal] = Field(None, gt=0, max_digits=15, decimal_places=2)
    closing_date: Optional[date] = None
    requirements: Optional[str] = Field(None, min_length=1)


class OpportunitySubmitRequest(BaseModel):
    pass


class OpportunityApproveRequest(BaseModel):
    preferred_partner: bool = False


class OpportunityRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1, max_length=1000)


class OpportunityInternalNoteRequest(BaseModel):
    internal_notes: str = Field(..., min_length=1)


class OppDocumentResponse(BaseModel):
    id: int
    file_name: str
    file_url: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class OpportunityResponse(BaseModel):
    id: int
    name: str
    customer_name: str
    region: str
    country: str
    city: str
    worth: Decimal
    closing_date: date
    requirements: str
    status: str
    preferred_partner: bool
    multi_partner_alert: bool
    rejection_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    submitted_by: int
    submitted_by_name: Optional[str] = None
    company_id: int
    company_name: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewer_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    documents: List[OppDocumentResponse] = []
    # AI enrichment (populated async after submit)
    ai_score: Optional[int] = None
    ai_reasoning: Optional[str] = None
    ai_scored_at: Optional[datetime] = None
    ai_duplicate_of_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OpportunityListResponse(BaseModel):
    id: int
    name: str
    customer_name: str
    country: str
    worth: Decimal
    closing_date: date
    status: str
    preferred_partner: bool
    multi_partner_alert: bool
    submitted_by_name: Optional[str] = None
    company_name: Optional[str] = None
    company_id: int
    submitted_at: Optional[datetime] = None
    ai_score: Optional[int] = None
    ai_reasoning: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
