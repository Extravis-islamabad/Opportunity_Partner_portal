from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


class ProductLineRequest(BaseModel):
    """One product on a deal, with the sizing the quote is built from.

    The counts are optional because a deal is usually qualified before they
    are known, and a zero would read as "none needed" rather than "not yet
    asked". `value` is this line's share of the deal and is deliberately not
    forced to sum to the opportunity's worth — a deal can include services
    that belong to no product line.
    """
    product: str = Field(..., max_length=50)
    device_count: Optional[int] = Field(None, ge=0)
    node_count: Optional[int] = Field(None, ge=0)
    value: Optional[Decimal] = Field(None, ge=0, max_digits=15, decimal_places=2)
    notes: Optional[str] = Field(None, max_length=2000)


class ProductLineResponse(BaseModel):
    product: str
    device_count: Optional[int] = None
    node_count: Optional[int] = None
    value: Optional[Decimal] = None
    notes: Optional[str] = None


class OpportunityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    customer_name: str = Field(..., min_length=1, max_length=200)
    region: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    city: str = Field(..., min_length=1, max_length=100)
    worth: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)
    # The currency the deal is done in. Absent means USD, which is what every
    # value in the system was implicitly before this existed.
    currency: Optional[str] = Field(None, pattern="^(USD|SAR|AED|PKR)$")
    closing_date: date
    requirements: str = Field(..., min_length=1)
    status: Optional[str] = Field("draft", pattern="^(draft|pending_review)$")
    # 2027 Target Plan fields
    industry: Optional[str] = Field(None, max_length=100)
    products: Optional[List[ProductLineRequest]] = None
    stage_probability: Optional[Decimal] = Field(None, ge=0, le=1, max_digits=3, decimal_places=2)
    time_frame: Optional[str] = Field(None, max_length=20)
    sales_rep_id: Optional[int] = None
    # The partner company the opportunity is registered for. A partner user
    # always registers for their own company and must leave this empty; a
    # sales rep registers on a partner's behalf and must name one. Which
    # partner holds the lock is the whole point of the registration, so the
    # service refuses to guess it.
    company_id: Optional[int] = None


class OpportunityUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    customer_name: Optional[str] = Field(None, min_length=1, max_length=200)
    region: Optional[str] = Field(None, min_length=1, max_length=100)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    worth: Optional[Decimal] = Field(None, gt=0, max_digits=15, decimal_places=2)
    currency: Optional[str] = Field(None, pattern="^(USD|SAR|AED|PKR)$")
    closing_date: Optional[date] = None
    requirements: Optional[str] = Field(None, min_length=1)
    industry: Optional[str] = Field(None, max_length=100)
    # Omitted means "leave the lines alone"; an empty list clears them.
    products: Optional[List[ProductLineRequest]] = None
    stage_probability: Optional[Decimal] = Field(None, ge=0, le=1, max_digits=3, decimal_places=2)
    time_frame: Optional[str] = Field(None, max_length=20)
    sales_rep_id: Optional[int] = None


class OpportunitySubmitRequest(BaseModel):
    pass


class OpportunityApproveRequest(BaseModel):
    preferred_partner: bool = False


class OpportunityRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1, max_length=1000)


LOSS_REASON_PATTERN = "^(price|competitor|no_budget|timing|technical_fit|no_decision)$"


class OpportunityCloseRequest(BaseModel):
    """Record the outcome of an approved opportunity.

    `won=False` requires a loss_reason — the whole point of closing a deal as
    lost is being able to count why. Notes are optional detail on top.
    """
    won: bool
    loss_reason: Optional[str] = Field(None, pattern=LOSS_REASON_PATTERN)
    loss_notes: Optional[str] = None


class LossReasonCount(BaseModel):
    reason: str
    label: str
    count: int
    total_worth: Decimal


class OpportunityInternalNoteRequest(BaseModel):
    internal_notes: str = Field(..., min_length=1)


class OppDocumentResponse(BaseModel):
    id: int
    file_name: str
    # A signed, short-lived download URL (see utils.file_tokens); Optional so
    # a missing stored path serialises as null rather than erroring.
    file_url: Optional[str] = None
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
    # What the deal is in, and what it is worth in the reporting currency at
    # the rate stamped on the record. Reports use the second; the customer
    # signed the first.
    currency: str = "USD"
    worth_usd: Optional[Decimal] = None
    closing_date: date
    requirements: str
    status: str
    preferred_partner: bool
    multi_partner_alert: bool
    rejection_reason: Optional[str] = None
    loss_reason: Optional[str] = None
    loss_reason_label: Optional[str] = None
    loss_notes: Optional[str] = None
    closed_outcome_at: Optional[datetime] = None
    # Set when this opportunity renews an expiring licence rather than being
    # new business. The UI uses it to say so; reporting uses it to tell renewal
    # revenue from new revenue.
    renewal_of_license_id: Optional[int] = None
    internal_notes: Optional[str] = None
    submitted_by: int
    submitted_by_name: Optional[str] = None
    company_id: int
    company_name: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewer_name: Optional[str] = None
    sales_rep_id: Optional[int] = None
    sales_rep_name: Optional[str] = None
    industry: Optional[str] = None
    # The full set of product lines, and a derived one-word summary for the
    # places that only have room for one (list columns, POC headers). The
    # summary is computed on the way out, so it cannot disagree with the lines.
    products: List[ProductLineResponse] = []
    product: Optional[str] = None
    stage_probability: Optional[Decimal] = None
    time_frame: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    documents: List[OppDocumentResponse] = []
    # AI enrichment (populated async after submit)
    ai_score: Optional[int] = None
    ai_reasoning: Optional[str] = None
    ai_scored_at: Optional[datetime] = None
    ai_duplicate_of_id: Optional[int] = None
    # Duplicate detection (populated synchronously on create/update/submit)
    customer_name_normalized: Optional[str] = None
    customer_domain: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PartnerCompanyOption(BaseModel):
    """A partner a sales rep can register an opportunity for."""
    id: int
    name: str
    company_type: str
    country: str
    tier: Optional[str] = None


class KnownCustomerOption(BaseModel):
    """A customer the portal already knows, offered to whoever is registering
    so the same customer is not typed six different ways. Free text is still
    accepted — this is a suggestion, not a constraint."""
    customer_name: str
    country: str
    city: Optional[str] = None
    region: Optional[str] = None
    # Who last registered them, when the suggestion comes from the pipeline.
    company_name: Optional[str] = None


class OpportunityListResponse(BaseModel):
    id: int
    name: str
    customer_name: str
    country: str
    worth: Decimal
    currency: str = "USD"
    worth_usd: Optional[Decimal] = None
    closing_date: date
    status: str
    preferred_partner: bool
    multi_partner_alert: bool
    submitted_by_name: Optional[str] = None
    company_name: Optional[str] = None
    company_id: int
    industry: Optional[str] = None
    # Names only — the list has no room for sizing, and the summary keeps the
    # column that was there before honest when a deal spans two products.
    products: List[str] = []
    product: Optional[str] = None
    stage_probability: Optional[Decimal] = None
    time_frame: Optional[str] = None
    sales_rep_id: Optional[int] = None
    sales_rep_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    ai_score: Optional[int] = None
    ai_reasoning: Optional[str] = None
    ai_duplicate_of_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}
