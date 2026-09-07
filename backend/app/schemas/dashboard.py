from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
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
    company_type: str
    # Null for a customer company.
    tier: Optional[str] = None
    opportunities_submitted: int
    opportunities_won: int
    opportunities_lost: int
    total_worth: Decimal
    approved_worth: Decimal
    lms_completion_rate: float


class TierProgress(BaseModel):
    """Progress toward the next tier, from tier_service — the one place the
    rules live. Both criteria are company-wide and both must be met.

    Replaces a per-user *course count*: a tier belongs to the company, so one
    keen individual finishing five courses no longer reads as the whole
    company being ready for platinum.
    """
    next_tier: Optional[str]
    opps_required: int
    opps_current: int
    opps_progress_pct: float
    # Company-wide completed/total enrolments, as a percentage.
    lms_rate_required: float
    lms_rate_current: float
    lms_progress_pct: float
    # Set only while the company is below the requirements for the tier it
    # already holds: the date the grace period runs out and the tier drops.
    # None is the normal case — the company qualifies for what it has.
    at_risk_until: Optional[str] = None
    at_risk_shortfall: Optional[str] = None
    # The weaker of the two — what actually stands between here and the next
    # tier. Averaging would flatter a company that has done all the training
    # and registered nothing.
    overall_progress_pct: float


class PartnerDashboardResponse(BaseModel):
    my_opportunities: int
    my_approved: int
    my_rejected: int
    my_pending: int
    my_drafts: int
    my_total_worth: Decimal
    my_approved_worth: Decimal
    # Null for a customer company — partner tier does not apply to it.
    company_tier: Optional[str] = None
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
    company_type: str
    # Null for a customer company — it can rank on pipeline but has no tier.
    tier: Optional[str] = None
    region: str
    opportunities_won: int
    approved_worth: Decimal


class FunnelStage(BaseModel):
    stage: str
    count: int


class LossReasonBreakdown(BaseModel):
    """Why deals were lost, over the scoped set. Only closed-lost
    opportunities appear — an open deal has no reason yet."""
    reason: str
    label: str
    count: int
    total_worth: Decimal


class AnalyticsResponse(BaseModel):
    regions: List[RegionBreakdown]
    tiers: List[TierDistribution]
    industries: List[IndustryBreakdown]
    top_companies: List[TopCompany]
    funnel: List[FunnelStage]
    # Empty until deals start being closed as lost — a system with no closed
    # losses genuinely has nothing to report here.
    loss_reasons: List[LossReasonBreakdown] = []
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
    company_type: str
    # Null for a customer company.
    tier: Optional[str] = None
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
    # Absent means USD — what every value in the system was implicitly before
    # multi-currency existed.
    currency: Optional[str] = Field(None, pattern="^(USD|SAR|AED|PKR)$")
    expected_close_date: str
    opportunity_id: Optional[int] = None
    # Client details — who the end client is beyond the name. Optional at the
    # API so registrations made through older clients stay accepted; the form
    # decides what it requires.
    client_email: Optional[str] = Field(None, max_length=255)
    client_website: Optional[str] = Field(None, max_length=255)
    client_contact: Optional[str] = Field(None, max_length=50)
    client_fax: Optional[str] = Field(None, max_length=50)
    client_address: Optional[str] = Field(None, max_length=500)
    individual_name: Optional[str] = Field(None, max_length=255)
    individual_department: Optional[str] = Field(None, max_length=255)
    individual_designation: Optional[str] = Field(None, max_length=255)
    # Tender or non-tender, with the supporting detail. The tender-only
    # fields are simply ignored by the UI for a non-tender deal.
    opportunity_type: Optional[str] = Field(None, pattern="^(tender|non_tender)$")
    opportunity_name: Optional[str] = Field(None, max_length=200)
    tender_number: Optional[str] = Field(None, max_length=100)
    tender_submission_date: Optional[str] = None
    mal_maf_required: Optional[bool] = None
    poc_required: Optional[bool] = None
    # Product names off the shared catalogue; unknown names are dropped
    # server-side rather than rejected.
    products: Optional[List[str]] = None


class DealRegistrationResponse(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    registered_by: int
    registered_by_name: Optional[str] = None
    customer_name: str
    deal_description: str
    estimated_value: Decimal
    # The currency the registration is in, and its value in the reporting
    # currency at the rate stamped when it was registered. Commission is
    # calculated from the second.
    currency: str = "USD"
    estimated_value_usd: Optional[Decimal] = None
    expected_close_date: str
    status: str
    exclusivity_start: Optional[str] = None
    exclusivity_end: Optional[str] = None
    # Days until exclusivity lapses. None once the window is gone or was never
    # granted — a negative number would imply protection that has run out but
    # still exists, and an expired registration has neither.
    days_left: Optional[int] = None
    expired_at: Optional[datetime] = None
    # Whether a request for more time is already waiting on a decision, so the
    # UI offers the action only where it would be accepted.
    extension_pending: bool = False
    rejection_reason: Optional[str] = None
    # Client details and tender / non-tender structure — see the create
    # request; null on registrations that predate the fields.
    client_email: Optional[str] = None
    client_website: Optional[str] = None
    client_contact: Optional[str] = None
    client_fax: Optional[str] = None
    client_address: Optional[str] = None
    individual_name: Optional[str] = None
    individual_department: Optional[str] = None
    individual_designation: Optional[str] = None
    opportunity_type: Optional[str] = None
    opportunity_name: Optional[str] = None
    tender_number: Optional[str] = None
    tender_submission_date: Optional[str] = None
    mal_maf_required: Optional[bool] = None
    poc_required: Optional[bool] = None
    products: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class DealApproveRequest(BaseModel):
    exclusivity_days: int = 90


class DealRejectRequest(BaseModel):
    rejection_reason: str


class ExtensionRequestCreate(BaseModel):
    """A partner asking for more exclusivity on a deal they registered.

    Capped at a year: an extension longer than the original window is a new
    registration, not an extension, and an unbounded number here would let a
    partner hold a customer indefinitely on one approval.
    """
    days: int = Field(..., ge=1, le=365)
    reason: Optional[str] = Field(None, max_length=2000)


class ExtensionDecisionRequest(BaseModel):
    """An admin's decision. `granted_days` may be fewer than were asked for;
    omit it to grant exactly what was requested."""
    approve: bool
    granted_days: Optional[int] = Field(None, ge=1, le=365)
    note: Optional[str] = Field(None, max_length=2000)


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
