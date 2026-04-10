from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal


class OverdueOpportunityItem(BaseModel):
    id: int
    name: str
    company_name: str
    closing_date: str
    worth: Decimal
    status: str


class DashboardStatsResponse(BaseModel):
    total_companies: int
    total_partners: int
    total_opportunities: int
    total_approved: int
    total_rejected: int
    total_pending: int
    total_worth: Decimal
    approved_worth: Decimal
    overdue_count: int = 0
    overdue_opportunities: List[OverdueOpportunityItem] = []
    pending_doc_requests: int = 0


class OpportunityStatusBreakdown(BaseModel):
    status: str
    count: int


class MonthlyOpportunityData(BaseModel):
    month: str
    submitted: int
    approved: int
    rejected: int


class CompanyPerformance(BaseModel):
    company_id: int
    company_name: str
    tier: str
    opportunities_submitted: int
    opportunities_won: int
    opportunities_lost: int
    total_worth: Decimal
    approved_worth: Decimal
    lms_completion_rate: float


class TierProgress(BaseModel):
    next_tier: Optional[str]
    opps_required: int
    opps_current: int
    courses_required: int
    courses_current: int
    opps_progress_pct: float
    courses_progress_pct: float


class PartnerDashboardResponse(BaseModel):
    my_opportunities: int
    my_approved: int
    my_rejected: int
    my_pending: int
    my_drafts: int
    my_total_worth: Decimal
    my_approved_worth: Decimal
    company_tier: str
    lms_courses_enrolled: int
    lms_courses_completed: int
    pending_doc_requests: int
    tier_progress: Optional[TierProgress] = None


class ChannelManagerCompanyBreakdown(BaseModel):
    company_id: int
    company_name: str
    tier: str
    partner_count: int
    pending_opportunities: int
    approved_opportunities: int
    pending_doc_requests: int


class ChannelManagerDashboardResponse(BaseModel):
    total_companies: int
    total_partners: int
    total_pending_opportunities: int
    total_approved_opportunities: int
    total_pending_doc_requests: int
    companies: List[ChannelManagerCompanyBreakdown]


class DealRegistrationCreateRequest(BaseModel):
    customer_name: str
    deal_description: str
    estimated_value: Decimal
    expected_close_date: str
    opportunity_id: Optional[int] = None


class DealRegistrationResponse(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    registered_by: int
    registered_by_name: Optional[str] = None
    customer_name: str
    deal_description: str
    estimated_value: Decimal
    expected_close_date: str
    status: str
    exclusivity_start: Optional[str] = None
    exclusivity_end: Optional[str] = None
    rejection_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class DealApproveRequest(BaseModel):
    exclusivity_days: int = 90


class DealRejectRequest(BaseModel):
    rejection_reason: str
