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


class RegionBreakdown(BaseModel):
    region: str
    company_count: int
    opportunity_count: int
    total_worth: Decimal
    approved_worth: Decimal


class TierDistribution(BaseModel):
    tier: str
    company_count: int
    total_worth: Decimal


class IndustryBreakdown(BaseModel):
    industry: str
    company_count: int
    opportunity_count: int


class TopCompany(BaseModel):
    company_id: int
    company_name: str
    tier: str
    region: str
    opportunities_won: int
    approved_worth: Decimal


class FunnelStage(BaseModel):
    stage: str
    count: int


class AnalyticsResponse(BaseModel):
    regions: List[RegionBreakdown]
    tiers: List[TierDistribution]
    industries: List[IndustryBreakdown]
    top_companies: List[TopCompany]
    funnel: List[FunnelStage]
    recent_activity: List["RecentActivityItem"]


class RecentActivityItem(BaseModel):
    id: int
    actor_name: str
    action: str
    entity_type: str
    entity_id: int
    timestamp: str


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


# ---------------------------------------------------------------------------
# 2027 Target Plan analytics
# ---------------------------------------------------------------------------

class ProductBreakdown(BaseModel):
    product: str
    opportunity_count: int
    total_worth: Decimal
    weighted_pipeline: Decimal  # sum(worth * stage_probability)


class OppIndustryBreakdown(BaseModel):
    industry: str
    opportunity_count: int
    total_worth: Decimal


class StageBreakdown(BaseModel):
    probability: float                # 0.10, 0.30, …, 1.00
    stage_label: str                  # "Raw Lead", "Payment Received", …
    opportunity_count: int
    total_worth: Decimal


class QuarterBreakdown(BaseModel):
    time_frame: str                   # "Q3 - 2027"
    opportunity_count: int
    total_worth: Decimal
    weighted_pipeline: Decimal


class SalesRepBreakdown(BaseModel):
    sales_rep_id: int
    sales_rep_name: str
    opportunity_count: int
    total_worth: Decimal
    weighted_pipeline: Decimal


class TargetPlanAnalyticsResponse(BaseModel):
    total_opportunities: int
    total_worth: Decimal
    weighted_pipeline: Decimal
    by_product: List[ProductBreakdown]
    by_industry: List[OppIndustryBreakdown]
    by_stage: List[StageBreakdown]
    by_quarter: List[QuarterBreakdown]
    by_sales_rep: List[SalesRepBreakdown]


# ==================== POC ====================

class PocStatusCount(BaseModel):
    status: str
    label: str
    count: int
    total_worth: Decimal


class PocStageProgress(BaseModel):
    """How many *running* POCs have cleared each stage. Reads as a funnel:
    every running POC has cleared VM Provisioning, fewer have cleared
    Deployment, and so on."""
    stage: str
    label: str
    completed_count: int
    pending_count: int
    # Mean days from POC start to this stage completing, measured across ALL
    # POCs that ever reached it (not just running ones) — so a stage can show
    # a duration while completed_count, which counts only running POCs, is 0.
    # None when no POC has reached the stage yet.
    avg_days_to_complete: Optional[float] = None


class PocCountryBreakdown(BaseModel):
    country: str
    running: int
    successful: int
    unsuccessful: int
    total_worth: Decimal


class PocSummaryResponse(BaseModel):
    total_pocs: int
    not_started: int
    running: int
    successful: int
    unsuccessful: int
    # Running POCs past their target end date.
    overdue: int
    # successful / (successful + unsuccessful) — closed POCs only, so an
    # in-flight POC never drags the rate down. None until one has closed.
    success_rate: Optional[float] = None
    avg_duration_days: Optional[float] = None
    running_worth: Decimal
    won_worth: Decimal
    by_status: List[PocStatusCount]
    by_stage: List[PocStageProgress]
    by_country: List[PocCountryBreakdown]


# ==================== Deployment ====================

class DeploymentMonthPoint(BaseModel):
    month: str
    started: int
    completed: int


class LicenseStatusCount(BaseModel):
    status: str
    label: str
    count: int
    device_count: int
    node_count: int


class ExpiringLicenseItem(BaseModel):
    opportunity_id: int
    customer_name: str
    company_name: Optional[str] = None
    country: Optional[str] = None
    license_expires_at: str
    days_until_expiry: int
    device_count: Optional[int] = None
    node_count: Optional[int] = None


class DeploymentAnalyticsResponse(BaseModel):
    # POC-side deployment activity
    active_pocs: int
    stage_funnel: List[PocStageProgress]
    monthly_activity: List[DeploymentMonthPoint]
    # Post-PO rollout
    total_devices: int
    total_nodes: int
    active_licenses: int
    licenses_by_status: List[LicenseStatusCount]
    expiring_soon: List[ExpiringLicenseItem]


# ==================== City funnel ====================

class CityFunnelCell(BaseModel):
    city: str
    country: Optional[str] = None
    # "Q1".."Q4", or "Unspecified" when time_frame is missing/unparseable.
    quarter: str
    stage: str
    stage_label: str
    opportunity_count: int
    total_worth: Decimal
    weighted_pipeline: Decimal


class CityFunnelResponse(BaseModel):
    cities: List[str]
    quarters: List[str]
    stages: List[str]
    stage_labels: dict[str, str]
    cells: List[CityFunnelCell]
    total_worth: Decimal
    weighted_pipeline: Decimal
