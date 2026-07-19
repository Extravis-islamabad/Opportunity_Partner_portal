from decimal import Decimal
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import select, func, case, extract, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import User, UserRole
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.doc_request import DocRequest, DocRequestStatus
from app.models.deal_registration import DealRegistration, DealStatus
from app.schemas.dashboard import (
    DashboardStatsResponse,
    OpportunityStatusBreakdown,
    MonthlyOpportunityData,
    CompanyPerformance,
    PartnerDashboardResponse,
    OverdueOpportunityItem,
    TierProgress,
    ChannelManagerDashboardResponse,
    ChannelManagerCompanyBreakdown,
    AnalyticsResponse,
    RegionBreakdown,
    TierDistribution,
    IndustryBreakdown,
    TopCompany,
    FunnelStage,
    RecentActivityItem,
    ProductBreakdown,
    OppIndustryBreakdown,
    StageBreakdown,
    QuarterBreakdown,
    SalesRepBreakdown,
    TargetPlanAnalyticsResponse,
    PocStatusCount,
    PocStageProgress,
    PocCountryBreakdown,
    PocSummaryResponse,
    DeploymentMonthPoint,
    LicenseStatusCount,
    ExpiringLicenseItem,
    DeploymentAnalyticsResponse,
    CityFunnelCell,
    CityFunnelResponse,
)
from app.models.audit_log import AuditLog
from app.models.poc import Poc, PocStatus, POC_STAGE_KEYS, POC_STAGE_LABELS
from app.models.customer_license import CustomerLicense, LicenseStatus
# Safe: poc_service does not import dashboard_service, so no cycle.
from app.services import poc_service


async def get_admin_dashboard_stats(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
) -> DashboardStatsResponse:
    """
    Returns admin dashboard stats. When `scope_company_ids` is None, the
    caller is a superadmin and sees the entire system. When it's a list,
    the caller is a channel manager and only data for those companies is
    counted (an empty list means they manage no companies → all-zero view).
    """
    is_scoped = scope_company_ids is not None

    # Base filters that apply to opportunity queries
    opp_scope: list = [Opportunity.deleted_at.is_(None)]
    if is_scoped:
        opp_scope.append(Opportunity.company_id.in_(scope_company_ids))

    company_filter: list = [Company.deleted_at.is_(None)]
    if is_scoped:
        company_filter.append(Company.id.in_(scope_company_ids))

    partner_filter: list = [User.role == UserRole.PARTNER, User.deleted_at.is_(None)]
    if is_scoped:
        partner_filter.append(User.company_id.in_(scope_company_ids))

    docreq_filter: list = [DocRequest.status == DocRequestStatus.PENDING, DocRequest.deleted_at.is_(None)]
    if is_scoped:
        docreq_filter.append(DocRequest.company_id.in_(scope_company_ids))

    company_count = await db.execute(select(func.count(Company.id)).where(*company_filter))
    partner_count = await db.execute(select(func.count(User.id)).where(*partner_filter))
    opp_count = await db.execute(select(func.count(Opportunity.id)).where(*opp_scope))
    approved_count = await db.execute(
        select(func.count(Opportunity.id)).where(*opp_scope, Opportunity.status == OpportunityStatus.APPROVED)
    )
    rejected_count = await db.execute(
        select(func.count(Opportunity.id)).where(*opp_scope, Opportunity.status == OpportunityStatus.REJECTED)
    )
    pending_count = await db.execute(
        select(func.count(Opportunity.id)).where(
            *opp_scope,
            Opportunity.status.in_([OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW]),
        )
    )
    total_worth = await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(*opp_scope)
    )
    approved_worth = await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(
            *opp_scope, Opportunity.status == OpportunityStatus.APPROVED
        )
    )

    # Overdue opportunities (scoped)
    overdue_filter = [
        Opportunity.closing_date < date.today(),
        Opportunity.status == OpportunityStatus.PENDING_REVIEW,
        Opportunity.deleted_at.is_(None),
    ]
    if is_scoped:
        overdue_filter.append(Opportunity.company_id.in_(scope_company_ids))
    overdue_count_result = await db.execute(
        select(func.count(Opportunity.id)).where(*overdue_filter)
    )
    overdue_rows = await db.execute(
        select(
            Opportunity.id,
            Opportunity.name,
            Company.name.label("company_name"),
            Opportunity.closing_date,
            Opportunity.worth,
            Opportunity.status,
        )
        .join(Company, Opportunity.company_id == Company.id)
        .where(*overdue_filter)
        .order_by(Opportunity.closing_date.asc())
        .limit(10)
    )
    overdue_items = [
        OverdueOpportunityItem(
            id=row[0],
            name=row[1],
            company_name=row[2],
            closing_date=str(row[3]),
            worth=row[4],
            status=row[5].value if hasattr(row[5], "value") else row[5],
        )
        for row in overdue_rows.all()
    ]

    pending_docs_count = await db.execute(select(func.count(DocRequest.id)).where(*docreq_filter))

    return DashboardStatsResponse(
        total_companies=company_count.scalar() or 0,
        total_partners=partner_count.scalar() or 0,
        total_opportunities=opp_count.scalar() or 0,
        total_approved=approved_count.scalar() or 0,
        total_rejected=rejected_count.scalar() or 0,
        total_pending=pending_count.scalar() or 0,
        total_worth=total_worth.scalar() or Decimal("0"),
        approved_worth=approved_worth.scalar() or Decimal("0"),
        overdue_count=overdue_count_result.scalar() or 0,
        overdue_opportunities=overdue_items,
        pending_doc_requests=pending_docs_count.scalar() or 0,
    )


async def get_opportunity_status_breakdown(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
) -> list[OpportunityStatusBreakdown]:
    filters = [Opportunity.deleted_at.is_(None)]
    if scope_company_ids is not None:
        filters.append(Opportunity.company_id.in_(scope_company_ids))
    result = await db.execute(
        select(Opportunity.status, func.count(Opportunity.id))
        .where(*filters)
        .group_by(Opportunity.status)
    )
    rows = result.all()
    return [
        OpportunityStatusBreakdown(status=row[0].value, count=row[1])
        for row in rows
    ]


async def get_monthly_opportunity_data(
    db: AsyncSession,
    months: int = 12,
    scope_company_ids: Optional[list[int]] = None,
) -> list[MonthlyOpportunityData]:
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=30 * (months - 1))

    filters = [
        Opportunity.deleted_at.is_(None),
        Opportunity.created_at >= start_date,
    ]
    if scope_company_ids is not None:
        filters.append(Opportunity.company_id.in_(scope_company_ids))

    month_col = func.to_char(Opportunity.created_at, 'YYYY-MM')
    result = await db.execute(
        select(
            month_col.label('month'),
            func.count(Opportunity.id).label('submitted'),
            func.sum(case((Opportunity.status == OpportunityStatus.APPROVED, 1), else_=0)).label('approved'),
            func.sum(case((Opportunity.status == OpportunityStatus.REJECTED, 1), else_=0)).label('rejected'),
        )
        .where(*filters)
        .group_by(month_col)
        .order_by(month_col)
    )
    rows = result.all()
    return [
        MonthlyOpportunityData(month=row[0], submitted=row[1], approved=row[2], rejected=row[3])
        for row in rows
    ]


async def get_company_performance(db: AsyncSession, company_id: int) -> CompanyPerformance:
    company_result = await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = company_result.scalar_one()

    submitted = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id, Opportunity.deleted_at.is_(None)
        )
    )
    won = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id,
            Opportunity.status == OpportunityStatus.APPROVED,
            Opportunity.deleted_at.is_(None),
        )
    )
    lost = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id,
            Opportunity.status == OpportunityStatus.REJECTED,
            Opportunity.deleted_at.is_(None),
        )
    )
    total_worth_result = await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(
            Opportunity.company_id == company_id, Opportunity.deleted_at.is_(None)
        )
    )
    approved_worth_result = await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(
            Opportunity.company_id == company_id,
            Opportunity.status == OpportunityStatus.APPROVED,
            Opportunity.deleted_at.is_(None),
        )
    )

    partner_ids_result = await db.execute(
        select(User.id).where(User.company_id == company_id, User.deleted_at.is_(None))
    )
    partner_ids = [r[0] for r in partner_ids_result.all()]

    lms_rate = 0.0
    if partner_ids:
        total_enrollments = await db.execute(
            select(func.count(Enrollment.id)).where(Enrollment.user_id.in_(partner_ids))
        )
        completed_enrollments = await db.execute(
            select(func.count(Enrollment.id)).where(
                Enrollment.user_id.in_(partner_ids),
                Enrollment.status == EnrollmentStatus.COMPLETED,
            )
        )
        total_e = total_enrollments.scalar() or 0
        completed_e = completed_enrollments.scalar() or 0
        if total_e > 0:
            lms_rate = round((completed_e / total_e) * 100, 1)

    return CompanyPerformance(
        company_id=company.id,
        company_name=company.name,
        tier=company.tier.value,
        opportunities_submitted=submitted.scalar() or 0,
        opportunities_won=won.scalar() or 0,
        opportunities_lost=lost.scalar() or 0,
        total_worth=total_worth_result.scalar() or Decimal("0"),
        approved_worth=approved_worth_result.scalar() or Decimal("0"),
        lms_completion_rate=lms_rate,
    )


async def get_partner_dashboard(db: AsyncSession, partner_user: User) -> PartnerDashboardResponse:
    base_filter = [Opportunity.submitted_by == partner_user.id, Opportunity.deleted_at.is_(None)]

    my_opps = (await db.execute(select(func.count(Opportunity.id)).where(*base_filter))).scalar() or 0
    my_approved = (await db.execute(
        select(func.count(Opportunity.id)).where(*base_filter, Opportunity.status == OpportunityStatus.APPROVED)
    )).scalar() or 0
    my_rejected = (await db.execute(
        select(func.count(Opportunity.id)).where(*base_filter, Opportunity.status == OpportunityStatus.REJECTED)
    )).scalar() or 0
    my_pending = (await db.execute(
        select(func.count(Opportunity.id)).where(
            *base_filter,
            Opportunity.status.in_([OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW]),
        )
    )).scalar() or 0
    my_drafts = (await db.execute(
        select(func.count(Opportunity.id)).where(*base_filter, Opportunity.status == OpportunityStatus.DRAFT)
    )).scalar() or 0
    my_total_worth = (await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(*base_filter)
    )).scalar() or Decimal("0")
    my_approved_worth = (await db.execute(
        select(func.coalesce(func.sum(Opportunity.worth), 0)).where(
            *base_filter, Opportunity.status == OpportunityStatus.APPROVED
        )
    )).scalar() or Decimal("0")

    company_tier = "silver"
    if partner_user.company_id:
        company_result = await db.execute(
            select(Company).where(Company.id == partner_user.company_id)
        )
        company = company_result.scalar_one_or_none()
        if company:
            company_tier = company.tier.value

    enrolled_count = (await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.user_id == partner_user.id)
    )).scalar() or 0
    completed_count = (await db.execute(
        select(func.count(Enrollment.id)).where(
            Enrollment.user_id == partner_user.id,
            Enrollment.status == EnrollmentStatus.COMPLETED,
        )
    )).scalar() or 0

    pending_docs = (await db.execute(
        select(func.count(DocRequest.id)).where(
            DocRequest.requested_by == partner_user.id,
            DocRequest.status == DocRequestStatus.PENDING,
            DocRequest.deleted_at.is_(None),
        )
    )).scalar() or 0

    # FIX 2: Tier progress calculation
    tier_thresholds = {
        "silver": {"opps": 1, "courses": 1},
        "gold": {"opps": 5, "courses": 3},
        "platinum": {"opps": 10, "courses": 5},
    }
    tier_order = ["silver", "gold", "platinum"]

    # Count approved opps for user's company
    company_approved_opps = 0
    if partner_user.company_id:
        company_approved_opps = (await db.execute(
            select(func.count(Opportunity.id)).where(
                Opportunity.company_id == partner_user.company_id,
                Opportunity.status == OpportunityStatus.APPROVED,
                Opportunity.deleted_at.is_(None),
            )
        )).scalar() or 0

    # completed_count already calculated above for LMS
    user_completed_courses = completed_count

    tier_progress = None
    current_idx = tier_order.index(company_tier) if company_tier in tier_order else 0
    if current_idx < len(tier_order) - 1:
        next_tier = tier_order[current_idx + 1]
        reqs = tier_thresholds[next_tier]
        opps_req = reqs["opps"]
        courses_req = reqs["courses"]
        opps_pct = min(round((company_approved_opps / opps_req) * 100, 1), 100.0) if opps_req > 0 else 100.0
        courses_pct = min(round((user_completed_courses / courses_req) * 100, 1), 100.0) if courses_req > 0 else 100.0
        tier_progress = TierProgress(
            next_tier=next_tier,
            opps_required=opps_req,
            opps_current=company_approved_opps,
            courses_required=courses_req,
            courses_current=user_completed_courses,
            opps_progress_pct=opps_pct,
            courses_progress_pct=courses_pct,
        )
    else:
        # Already at platinum
        tier_progress = TierProgress(
            next_tier=None,
            opps_required=0,
            opps_current=company_approved_opps,
            courses_required=0,
            courses_current=user_completed_courses,
            opps_progress_pct=100.0,
            courses_progress_pct=100.0,
        )

    return PartnerDashboardResponse(
        my_opportunities=my_opps,
        my_approved=my_approved,
        my_rejected=my_rejected,
        my_pending=my_pending,
        my_drafts=my_drafts,
        my_total_worth=my_total_worth,
        my_approved_worth=my_approved_worth,
        company_tier=company_tier,
        lms_courses_enrolled=enrolled_count,
        lms_courses_completed=completed_count,
        pending_doc_requests=pending_docs,
        tier_progress=tier_progress,
    )


async def get_channel_manager_dashboard(
    db: AsyncSession, user_id: int
) -> ChannelManagerDashboardResponse:
    # Get per-company breakdown using SQL aggregation
    result = await db.execute(
        select(
            Company.id,
            Company.name,
            Company.tier,
            func.count(func.distinct(User.id)).label("partner_count"),
            func.sum(case(
                (Opportunity.status.in_([OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW]), 1),
                else_=0,
            )).label("pending_opps"),
            func.sum(case(
                (Opportunity.status == OpportunityStatus.APPROVED, 1),
                else_=0,
            )).label("approved_opps"),
        )
        .outerjoin(User, (User.company_id == Company.id) & (User.deleted_at.is_(None)) & (User.role == UserRole.PARTNER))
        .outerjoin(Opportunity, (Opportunity.company_id == Company.id) & (Opportunity.deleted_at.is_(None)))
        .where(
            Company.channel_manager_id == user_id,
            Company.deleted_at.is_(None),
        )
        .group_by(Company.id, Company.name, Company.tier)
    )
    rows = result.all()

    # Get pending doc request counts per company
    doc_result = await db.execute(
        select(
            DocRequest.company_id,
            func.count(DocRequest.id),
        )
        .where(
            DocRequest.status == DocRequestStatus.PENDING,
            DocRequest.deleted_at.is_(None),
            DocRequest.company_id.in_([row[0] for row in rows]) if rows else False,
        )
        .group_by(DocRequest.company_id)
    )
    doc_counts = {row[0]: row[1] for row in doc_result.all()}

    companies = []
    total_partners = 0
    total_pending_opps = 0
    total_approved_opps = 0
    total_pending_docs = 0

    for row in rows:
        company_id = row[0]
        partner_count = row[3] or 0
        pending_opps = row[4] or 0
        approved_opps = row[5] or 0
        pending_docs = doc_counts.get(company_id, 0)

        total_partners += partner_count
        total_pending_opps += pending_opps
        total_approved_opps += approved_opps
        total_pending_docs += pending_docs

        companies.append(ChannelManagerCompanyBreakdown(
            company_id=company_id,
            company_name=row[1],
            tier=row[2].value if hasattr(row[2], "value") else row[2],
            partner_count=partner_count,
            pending_opportunities=pending_opps,
            approved_opportunities=approved_opps,
            pending_doc_requests=pending_docs,
        ))

    return ChannelManagerDashboardResponse(
        total_companies=len(companies),
        total_partners=total_partners,
        total_pending_opportunities=total_pending_opps,
        total_approved_opportunities=total_approved_opps,
        total_pending_doc_requests=total_pending_docs,
        companies=companies,
    )


async def get_partner_timeline(
    db: AsyncSession, partner_id: int, months: int = 6
) -> list[MonthlyOpportunityData]:
    """Per-partner monthly submitted/approved/rejected for the partner dashboard
    area chart. Returns last `months` months of activity."""
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=30 * (months - 1))

    month_col = func.to_char(Opportunity.created_at, 'YYYY-MM')
    result = await db.execute(
        select(
            month_col.label('month'),
            func.count(Opportunity.id).label('submitted'),
            func.sum(case((Opportunity.status == OpportunityStatus.APPROVED, 1), else_=0)).label('approved'),
            func.sum(case((Opportunity.status == OpportunityStatus.REJECTED, 1), else_=0)).label('rejected'),
        )
        .where(
            Opportunity.submitted_by == partner_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.created_at >= start_date,
        )
        .group_by(month_col)
        .order_by(month_col)
    )
    rows = result.all()
    return [
        MonthlyOpportunityData(month=row[0], submitted=row[1] or 0, approved=row[2] or 0, rejected=row[3] or 0)
        for row in rows
    ]


async def get_admin_analytics(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
) -> AnalyticsResponse:
    """
    Aggregations for the admin dashboard charts. One service call returns
    everything the dashboard needs to draw region/tier/industry/funnel
    breakdowns plus the top-companies leaderboard and recent activity feed.

    When `scope_company_ids` is None → superadmin view (everything).
    When it's a list → channel-manager view scoped to those companies.
    """
    is_scoped = scope_company_ids is not None
    company_filter = [Company.deleted_at.is_(None)]
    if is_scoped:
        company_filter.append(Company.id.in_(scope_company_ids))
    # ---- Region breakdown ---------------------------------------------------
    region_rows = (await db.execute(
        select(
            Company.region,
            func.count(func.distinct(Company.id)).label("company_count"),
            func.count(Opportunity.id).label("opp_count"),
            func.coalesce(func.sum(Opportunity.worth), 0).label("total_worth"),
            func.coalesce(
                func.sum(
                    case(
                        (Opportunity.status == OpportunityStatus.APPROVED, Opportunity.worth),
                        else_=0,
                    )
                ),
                0,
            ).label("approved_worth"),
        )
        .select_from(Company)
        .outerjoin(
            Opportunity,
            (Opportunity.company_id == Company.id) & (Opportunity.deleted_at.is_(None)),
        )
        .where(*company_filter)
        .group_by(Company.region)
        .order_by(func.coalesce(func.sum(Opportunity.worth), 0).desc())
    )).all()
    regions = [
        RegionBreakdown(
            region=row[0],
            company_count=row[1],
            opportunity_count=row[2] or 0,
            total_worth=row[3],
            approved_worth=row[4],
        )
        for row in region_rows
    ]

    # ---- Tier distribution --------------------------------------------------
    tier_rows = (await db.execute(
        select(
            Company.tier,
            func.count(func.distinct(Company.id)).label("company_count"),
            func.coalesce(func.sum(Opportunity.worth), 0).label("total_worth"),
        )
        .select_from(Company)
        .outerjoin(
            Opportunity,
            (Opportunity.company_id == Company.id) & (Opportunity.deleted_at.is_(None)),
        )
        .where(*company_filter)
        .group_by(Company.tier)
    )).all()
    tiers = [
        TierDistribution(
            tier=row[0].value if hasattr(row[0], "value") else row[0],
            company_count=row[1],
            total_worth=row[2],
        )
        for row in tier_rows
    ]

    # ---- Industry breakdown -------------------------------------------------
    industry_rows = (await db.execute(
        select(
            Company.industry,
            func.count(func.distinct(Company.id)).label("company_count"),
            func.count(Opportunity.id).label("opp_count"),
        )
        .select_from(Company)
        .outerjoin(
            Opportunity,
            (Opportunity.company_id == Company.id) & (Opportunity.deleted_at.is_(None)),
        )
        .where(*company_filter)
        .group_by(Company.industry)
        .order_by(func.count(Opportunity.id).desc())
        .limit(8)
    )).all()
    industries = [
        IndustryBreakdown(
            industry=row[0],
            company_count=row[1],
            opportunity_count=row[2] or 0,
        )
        for row in industry_rows
    ]

    # ---- Top 5 performing companies (by approved worth) --------------------
    top_rows = (await db.execute(
        select(
            Company.id,
            Company.name,
            Company.tier,
            Company.region,
            func.count(
                case((Opportunity.status == OpportunityStatus.APPROVED, 1))
            ).label("won"),
            func.coalesce(
                func.sum(
                    case(
                        (Opportunity.status == OpportunityStatus.APPROVED, Opportunity.worth),
                        else_=0,
                    )
                ),
                0,
            ).label("approved_worth"),
        )
        .select_from(Company)
        .outerjoin(
            Opportunity,
            (Opportunity.company_id == Company.id) & (Opportunity.deleted_at.is_(None)),
        )
        .where(*company_filter)
        .group_by(Company.id, Company.name, Company.tier, Company.region)
        .order_by(
            func.coalesce(
                func.sum(
                    case(
                        (Opportunity.status == OpportunityStatus.APPROVED, Opportunity.worth),
                        else_=0,
                    )
                ),
                0,
            ).desc()
        )
        .limit(6)
    )).all()
    top_companies = [
        TopCompany(
            company_id=row[0],
            company_name=row[1],
            tier=row[2].value if hasattr(row[2], "value") else row[2],
            region=row[3],
            opportunities_won=row[4] or 0,
            approved_worth=row[5],
        )
        for row in top_rows
    ]

    # ---- Conversion funnel --------------------------------------------------
    funnel_counts = {}
    funnel_base = [Opportunity.deleted_at.is_(None)]
    if is_scoped:
        funnel_base.append(Opportunity.company_id.in_(scope_company_ids))
    for status in [
        OpportunityStatus.DRAFT,
        OpportunityStatus.PENDING_REVIEW,
        OpportunityStatus.UNDER_REVIEW,
        OpportunityStatus.APPROVED,
    ]:
        c = (await db.execute(
            select(func.count(Opportunity.id)).where(
                *funnel_base,
                Opportunity.status == status,
            )
        )).scalar() or 0
        funnel_counts[status.value] = c

    funnel = [
        FunnelStage(stage="Draft", count=funnel_counts.get("draft", 0)),
        FunnelStage(stage="Submitted", count=funnel_counts.get("pending_review", 0)),
        FunnelStage(stage="In Review", count=funnel_counts.get("under_review", 0)),
        FunnelStage(stage="Approved", count=funnel_counts.get("approved", 0)),
    ]

    # ---- Recent activity (last 10 audit log entries) -----------------------
    # When scoped: only show actions taken by partners of managed companies
    # (so a channel manager doesn't see audit logs for partners they don't
    # manage). Superadmin sees the global feed.
    activity_query = (
        select(
            AuditLog.id,
            User.full_name,
            AuditLog.action,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.timestamp,
        )
        .join(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(10)
    )
    if is_scoped:
        # Get user ids of partners belonging to managed companies
        scoped_user_rows = (await db.execute(
            select(User.id).where(User.company_id.in_(scope_company_ids))
        )).all()
        scoped_user_ids = [r[0] for r in scoped_user_rows]
        activity_query = activity_query.where(AuditLog.user_id.in_(scoped_user_ids or [-1]))
    activity_rows = (await db.execute(activity_query)).all()
    recent_activity = [
        RecentActivityItem(
            id=row[0],
            actor_name=row[1],
            action=row[2],
            entity_type=row[3],
            entity_id=row[4],
            timestamp=row[5].isoformat(),
        )
        for row in activity_rows
    ]

    return AnalyticsResponse(
        regions=regions,
        tiers=tiers,
        industries=industries,
        top_companies=top_companies,
        funnel=funnel,
        recent_activity=recent_activity,
    )


STAGE_LABELS = {
    0.1: "Raw Lead",
    0.3: "POC Engaged / Tender Specs",
    0.6: "POC Successful / Budget Approved",
    0.7: "Price Submitted / Negotiation",
    0.9: "PO Received",
    1.0: "Payment Received",
}


def _stage_label(probability: Optional[Decimal]) -> str:
    if probability is None:
        return "Unspecified"
    key = round(float(probability), 1)
    return STAGE_LABELS.get(key, f"Stage {key:.1f}")


async def get_target_plan_analytics(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
) -> TargetPlanAnalyticsResponse:
    """Pipeline analytics driven by the 2027 Target Plan dimensions:
    product, customer industry, stage probability, time-frame quarter, and
    Extravis sales rep. Weighted pipeline = sum(worth * stage_probability).
    """
    base: list = [Opportunity.deleted_at.is_(None), Opportunity.status != OpportunityStatus.REMOVED]
    if scope_company_ids is not None:
        base.append(Opportunity.company_id.in_(scope_company_ids))

    weighted_expr = func.coalesce(func.sum(Opportunity.worth * Opportunity.stage_probability), 0)
    worth_expr = func.coalesce(func.sum(Opportunity.worth), 0)

    # Totals
    total_q = (await db.execute(
        select(
            func.count(Opportunity.id),
            worth_expr,
            weighted_expr,
        ).where(*base)
    )).one()

    # By product
    by_product_rows = (await db.execute(
        select(
            func.coalesce(Opportunity.product, "Unspecified"),
            func.count(Opportunity.id),
            worth_expr,
            weighted_expr,
        )
        .where(*base)
        .group_by(Opportunity.product)
        .order_by(weighted_expr.desc())
    )).all()
    by_product = [
        ProductBreakdown(
            product=row[0],
            opportunity_count=row[1],
            total_worth=row[2],
            weighted_pipeline=row[3],
        )
        for row in by_product_rows
    ]

    # By industry (from opportunity, not company)
    by_industry_rows = (await db.execute(
        select(
            func.coalesce(Opportunity.industry, "Unspecified"),
            func.count(Opportunity.id),
            worth_expr,
        )
        .where(*base)
        .group_by(Opportunity.industry)
        .order_by(worth_expr.desc())
    )).all()
    by_industry = [
        OppIndustryBreakdown(
            industry=row[0],
            opportunity_count=row[1],
            total_worth=row[2],
        )
        for row in by_industry_rows
    ]

    # By stage probability
    by_stage_rows = (await db.execute(
        select(
            Opportunity.stage_probability,
            func.count(Opportunity.id),
            worth_expr,
        )
        .where(*base)
        .group_by(Opportunity.stage_probability)
        .order_by(Opportunity.stage_probability.asc().nulls_last())
    )).all()
    by_stage = [
        StageBreakdown(
            probability=float(row[0]) if row[0] is not None else 0.0,
            stage_label=_stage_label(row[0]),
            opportunity_count=row[1],
            total_worth=row[2],
        )
        for row in by_stage_rows
    ]

    # By quarter / time frame
    by_quarter_rows = (await db.execute(
        select(
            func.coalesce(Opportunity.time_frame, "Unspecified"),
            func.count(Opportunity.id),
            worth_expr,
            weighted_expr,
        )
        .where(*base)
        .group_by(Opportunity.time_frame)
        .order_by(func.coalesce(Opportunity.time_frame, "Unspecified").asc())
    )).all()
    by_quarter = [
        QuarterBreakdown(
            time_frame=row[0],
            opportunity_count=row[1],
            total_worth=row[2],
            weighted_pipeline=row[3],
        )
        for row in by_quarter_rows
    ]

    # By sales rep (Extravis Team)
    by_rep_rows = (await db.execute(
        select(
            User.id,
            User.full_name,
            func.count(Opportunity.id),
            worth_expr,
            weighted_expr,
        )
        .select_from(Opportunity)
        .join(User, User.id == Opportunity.sales_rep_id)
        .where(*base, Opportunity.sales_rep_id.is_not(None))
        .group_by(User.id, User.full_name)
        .order_by(weighted_expr.desc())
    )).all()
    by_sales_rep = [
        SalesRepBreakdown(
            sales_rep_id=row[0],
            sales_rep_name=row[1],
            opportunity_count=row[2],
            total_worth=row[3],
            weighted_pipeline=row[4],
        )
        for row in by_rep_rows
    ]

    return TargetPlanAnalyticsResponse(
        total_opportunities=total_q[0] or 0,
        total_worth=total_q[1] or Decimal("0"),
        weighted_pipeline=total_q[2] or Decimal("0"),
        by_product=by_product,
        by_industry=by_industry,
        by_stage=by_stage,
        by_quarter=by_quarter,
        by_sales_rep=by_sales_rep,
    )


async def evaluate_tier_upgrade(db: AsyncSession, company_id: int) -> str | None:
    from app.models.partner_tier import PartnerTierHistory

    company_result = await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = company_result.scalar_one_or_none()
    if not company:
        return None

    approved_count = (await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id,
            Opportunity.status == OpportunityStatus.APPROVED,
            Opportunity.deleted_at.is_(None),
        )
    )).scalar() or 0

    performance = await get_company_performance(db, company_id)
    lms_rate = performance.lms_completion_rate

    current_tier = company.tier.value
    new_tier = current_tier

    if approved_count >= 20 and lms_rate >= 80:
        new_tier = "platinum"
    elif approved_count >= 10 and lms_rate >= 50:
        new_tier = "gold"
    else:
        new_tier = "silver"

    tier_order = {"silver": 0, "gold": 1, "platinum": 2}
    if tier_order.get(new_tier, 0) > tier_order.get(current_tier, 0):
        from app.models.company import PartnerTier
        company.tier = PartnerTier(new_tier)

        tier_record = PartnerTierHistory(
            company_id=company_id,
            previous_tier=current_tier,
            new_tier=new_tier,
            reason=f"Auto-upgrade: {approved_count} approved opportunities, {lms_rate}% LMS completion",
        )
        db.add(tier_record)
        await db.flush()
        return new_tier

    return None


# ===========================================================================
# POC / deployment / city funnel
# ===========================================================================

POC_STATUS_LABELS = {
    "not_started": "Not Started",
    "running": "Running",
    "successful": "Successful",
    "unsuccessful": "Unsuccessful",
}

LICENSE_STATUS_LABELS = {
    "pending_activation": "Pending Activation",
    "active": "Active",
    "expiring_soon": "Expiring Soon",
    "expired": "Expired",
}


def _poc_base_filters(scope_company_ids: Optional[list[int]], sales_rep_id: Optional[int]) -> list:
    """Shared scoping for every POC aggregation.

    `scope_company_ids=[]` (a channel manager with no companies) must yield
    nothing — hence the explicit `is not None` check rather than a truthiness
    test, which would silently drop the filter and expose everything.
    """
    filters: list = [Poc.deleted_at.is_(None), Opportunity.deleted_at.is_(None)]
    if scope_company_ids is not None:
        filters.append(Opportunity.company_id.in_(scope_company_ids))
    if sales_rep_id is not None:
        filters.append(Opportunity.sales_rep_id == sales_rep_id)
    return filters


async def get_poc_summary(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
    sales_rep_id: Optional[int] = None,
) -> PocSummaryResponse:
    """POC widgets: status counts, the five-stage funnel, and per-country
    split. Backs the POC block on the admin dashboard."""
    today = date.today()
    base = _poc_base_filters(scope_company_ids, sales_rep_id)

    # Status counts + worth
    status_rows = (await db.execute(
        select(
            Poc.status,
            func.count(Poc.id),
            func.coalesce(func.sum(Opportunity.worth), 0),
        )
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*base)
        .group_by(Poc.status)
    )).all()

    counts = {s: 0 for s in POC_STATUS_LABELS}
    worths = {s: Decimal(0) for s in POC_STATUS_LABELS}
    for row in status_rows:
        key = row[0].value if hasattr(row[0], "value") else str(row[0])
        counts[key] = row[1]
        worths[key] = row[2] or Decimal(0)

    by_status = [
        PocStatusCount(status=k, label=v, count=counts[k], total_worth=worths[k])
        for k, v in POC_STATUS_LABELS.items()
    ]

    total = sum(counts.values())
    closed = counts["successful"] + counts["unsuccessful"]
    # Rate over *closed* POCs only — an in-flight POC isn't a failure yet.
    success_rate = (counts["successful"] / closed * 100) if closed else None

    # Average duration over closed POCs that have both dates.
    avg_duration = (await db.execute(
        select(func.avg(Poc.end_date - Poc.start_date))
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*base, Poc.end_date.is_not(None), Poc.start_date.is_not(None))
    )).scalar()

    overdue = (await db.execute(
        select(func.count(Poc.id))
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(
            *base,
            Poc.closed_at.is_(None),
            Poc.target_end_date.is_not(None),
            Poc.target_end_date < today,
        )
    )).scalar() or 0

    # Stage funnel across running POCs.
    running_filter = [*base, Poc.status == PocStatus.RUNNING]
    running_total = (await db.execute(
        select(func.count(Poc.id))
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*running_filter)
    )).scalar() or 0

    by_stage: list[PocStageProgress] = []
    for key in POC_STAGE_KEYS:
        col = getattr(Poc, key + "_completed_at")
        done = (await db.execute(
            select(func.count(Poc.id))
            .select_from(Poc)
            .join(Opportunity, Poc.opportunity_id == Opportunity.id)
            .where(*running_filter, col.is_not(None))
        )).scalar() or 0
        avg_days = (await db.execute(
            select(func.avg(col - Poc.start_date))
            .select_from(Poc)
            .join(Opportunity, Poc.opportunity_id == Opportunity.id)
            .where(*base, col.is_not(None), Poc.start_date.is_not(None))
        )).scalar()
        by_stage.append(PocStageProgress(
            stage=key,
            label=POC_STAGE_LABELS[key],
            completed_count=done,
            pending_count=max(running_total - done, 0),
            avg_days_to_complete=float(avg_days) if avg_days is not None else None,
        ))

    # Per-country split
    country_rows = (await db.execute(
        select(
            Opportunity.country,
            func.sum(case((Poc.status == PocStatus.RUNNING, 1), else_=0)),
            func.sum(case((Poc.status == PocStatus.SUCCESSFUL, 1), else_=0)),
            func.sum(case((Poc.status == PocStatus.UNSUCCESSFUL, 1), else_=0)),
            func.coalesce(func.sum(Opportunity.worth), 0),
        )
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*base)
        .group_by(Opportunity.country)
        .order_by(func.count(Poc.id).desc())
    )).all()

    by_country = [
        PocCountryBreakdown(
            country=r[0] or "Unspecified",
            running=r[1] or 0,
            successful=r[2] or 0,
            unsuccessful=r[3] or 0,
            total_worth=r[4] or Decimal(0),
        )
        for r in country_rows
    ]

    return PocSummaryResponse(
        total_pocs=total,
        not_started=counts["not_started"],
        running=counts["running"],
        successful=counts["successful"],
        unsuccessful=counts["unsuccessful"],
        overdue=overdue,
        success_rate=round(success_rate, 1) if success_rate is not None else None,
        avg_duration_days=round(float(avg_duration), 1) if avg_duration is not None else None,
        running_worth=worths["running"],
        won_worth=worths["successful"],
        by_status=by_status,
        by_stage=by_stage,
        by_country=by_country,
    )


async def get_deployment_analytics(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
    sales_rep_id: Optional[int] = None,
    months: int = 12,
) -> DeploymentAnalyticsResponse:
    """Backs the Deployment tab: POC stage throughput plus post-PO device /
    node rollout and licence expiry."""
    today = date.today()
    base = _poc_base_filters(scope_company_ids, sales_rep_id)

    summary = await get_poc_summary(db, scope_company_ids, sales_rep_id)

    # Monthly: POCs started vs closed. Two separate groupings because a POC
    # started in March and closed in June belongs to both months.
    # Bind each to_char to a single expression object and reuse it in both
    # SELECT and GROUP BY. Inlining func.to_char() twice emits two separate
    # bind params ($1, $2), which Postgres treats as different expressions —
    # "column pocs.start_date must appear in the GROUP BY clause".
    start_month = func.to_char(Poc.start_date, "YYYY-MM")
    end_month = func.to_char(Poc.end_date, "YYYY-MM")

    started_rows = (await db.execute(
        select(start_month, func.count(Poc.id))
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*base, Poc.start_date.is_not(None))
        .group_by(start_month)
    )).all()
    closed_rows = (await db.execute(
        select(end_month, func.count(Poc.id))
        .select_from(Poc)
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(*base, Poc.end_date.is_not(None))
        .group_by(end_month)
    )).all()

    started_map = {r[0]: r[1] for r in started_rows}
    closed_map = {r[0]: r[1] for r in closed_rows}

    # Emit a continuous month axis so the chart doesn't skip quiet months.
    keys: list[str] = []
    cursor = today.replace(day=1)
    for _ in range(months):
        keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)

    monthly = [
        DeploymentMonthPoint(
            month=key,
            started=started_map.get(key, 0),
            completed=closed_map.get(key, 0),
        )
        for key in reversed(keys)
    ]

    # Post-PO licences
    lic_base: list = [CustomerLicense.deleted_at.is_(None), Opportunity.deleted_at.is_(None)]
    if scope_company_ids is not None:
        lic_base.append(Opportunity.company_id.in_(scope_company_ids))
    if sales_rep_id is not None:
        lic_base.append(Opportunity.sales_rep_id == sales_rep_id)

    # Group by the *derived* status, not CustomerLicense.status. The stored
    # column is only a snapshot of what was true when the row was last saved,
    # so grouping on it reports licences as active long after they expired.
    lic_status = poc_service.license_status_expr(today)
    lic_rows = (await db.execute(
        select(
            lic_status,
            func.count(CustomerLicense.id),
            func.coalesce(func.sum(CustomerLicense.device_count), 0),
            func.coalesce(func.sum(CustomerLicense.node_count), 0),
        )
        .select_from(CustomerLicense)
        .join(Opportunity, CustomerLicense.opportunity_id == Opportunity.id)
        .where(*lic_base)
        .group_by(lic_status)
    )).all()

    lic_counts = {s: (0, 0, 0) for s in LICENSE_STATUS_LABELS}
    for r in lic_rows:
        key = r[0].value if hasattr(r[0], "value") else str(r[0])
        lic_counts[key] = (r[1], r[2] or 0, r[3] or 0)

    licenses_by_status = [
        LicenseStatusCount(
            status=k, label=v,
            count=lic_counts[k][0],
            device_count=lic_counts[k][1],
            node_count=lic_counts[k][2],
        )
        for k, v in LICENSE_STATUS_LABELS.items()
    ]

    # Devices/nodes only count once a licence is live — pending and expired
    # rows aren't deployed capacity.
    live = ("active", "expiring_soon")
    total_devices = sum(lic_counts[s][1] for s in live)
    total_nodes = sum(lic_counts[s][2] for s in live)
    active_licenses = sum(lic_counts[s][0] for s in live)

    # Upcoming expiries — soonest first.
    exp_rows = (await db.execute(
        select(CustomerLicense, Opportunity, Company)
        .select_from(CustomerLicense)
        .join(Opportunity, CustomerLicense.opportunity_id == Opportunity.id)
        .outerjoin(Company, Opportunity.company_id == Company.id)
        .where(
            *lic_base,
            CustomerLicense.license_expires_at.is_not(None),
            CustomerLicense.license_expires_at >= today,
            CustomerLicense.license_expires_at <= today + timedelta(days=90),
        )
        .order_by(CustomerLicense.license_expires_at.asc())
        .limit(10)
    )).all()

    expiring_soon = [
        ExpiringLicenseItem(
            opportunity_id=opp.id,
            customer_name=opp.customer_name,
            company_name=comp.name if comp else None,
            country=opp.country,
            license_expires_at=str(lic.license_expires_at),
            days_until_expiry=(lic.license_expires_at - today).days,
            device_count=lic.device_count,
            node_count=lic.node_count,
        )
        for lic, opp, comp in exp_rows
    ]

    return DeploymentAnalyticsResponse(
        active_pocs=summary.running,
        stage_funnel=summary.by_stage,
        monthly_activity=monthly,
        total_devices=total_devices,
        total_nodes=total_nodes,
        active_licenses=active_licenses,
        licenses_by_status=licenses_by_status,
        expiring_soon=expiring_soon,
    )


async def get_city_funnel(
    db: AsyncSession,
    scope_company_ids: Optional[list[int]] = None,
    year: Optional[int] = None,
) -> CityFunnelResponse:
    """Sales-funnel value broken down by city and quarter.

    Quarter comes out of the `time_frame` string ("Q3 - 2027"), which is the
    Excel target-plan format. We pull the digit out with a regex rather than
    parse the whole string, so odd spacing ("Q3-2027", "q3 2027") still lands
    in the right bucket. Rows with no parseable quarter group under
    "Unspecified" instead of vanishing from the totals.
    """
    base: list = [
        Opportunity.deleted_at.is_(None),
        Opportunity.status != OpportunityStatus.REMOVED,
    ]
    if scope_company_ids is not None:
        base.append(Opportunity.company_id.in_(scope_company_ids))
    if year is not None:
        base.append(Opportunity.time_frame.ilike("%" + str(year) + "%"))

    # `||` not concat(): Postgres' concat() *ignores* NULLs, so
    # concat('Q', NULL) returns 'Q' and the coalesce below would never fire —
    # every unparseable time_frame would land in a phantom quarter named "Q".
    # `||` propagates NULL, so those rows correctly fall through to
    # "Unspecified".
    quarter_expr = func.coalesce(
        literal("Q").op("||")(func.substring(Opportunity.time_frame, "[Qq]([1-4])")),
        "Unspecified",
    )
    worth_expr = func.coalesce(func.sum(Opportunity.worth), 0)
    weighted_expr = func.coalesce(
        func.sum(Opportunity.worth * Opportunity.stage_probability), 0
    )

    rows = (await db.execute(
        select(
            Opportunity.city,
            Opportunity.country,
            quarter_expr,
            Opportunity.stage_probability,
            func.count(Opportunity.id),
            worth_expr,
            weighted_expr,
        )
        .where(*base)
        .group_by(
            Opportunity.city,
            Opportunity.country,
            quarter_expr,
            Opportunity.stage_probability,
        )
        .order_by(worth_expr.desc())
    )).all()

    cells: list[CityFunnelCell] = []
    for city, country, quarter, prob, count, worth, weighted in rows:
        stage_key = "{:.1f}".format(float(prob)) if prob is not None else "unspecified"
        cells.append(CityFunnelCell(
            city=city or "Unspecified",
            country=country,
            quarter=quarter or "Unspecified",
            stage=stage_key,
            stage_label=_stage_label(prob),
            opportunity_count=count,
            total_worth=worth or Decimal(0),
            weighted_pipeline=weighted or Decimal(0),
        ))

    # Order cities by total value so the chart leads with what matters.
    city_totals: dict[str, Decimal] = {}
    for c in cells:
        city_totals[c.city] = city_totals.get(c.city, Decimal(0)) + c.total_worth
    cities = sorted(city_totals, key=lambda c: city_totals[c], reverse=True)

    present_quarters = {c.quarter for c in cells}
    quarters = [q for q in ("Q1", "Q2", "Q3", "Q4") if q in present_quarters]
    if "Unspecified" in present_quarters:
        quarters.append("Unspecified")

    stages = ["{:.1f}".format(p) for p in sorted(STAGE_LABELS)]
    stage_labels = {"{:.1f}".format(p): label for p, label in STAGE_LABELS.items()}
    if any(c.stage == "unspecified" for c in cells):
        stages.append("unspecified")
        stage_labels["unspecified"] = "Unspecified"

    return CityFunnelResponse(
        cities=cities,
        quarters=quarters,
        stages=stages,
        stage_labels=stage_labels,
        cells=cells,
        total_worth=sum((c.total_worth for c in cells), Decimal(0)),
        weighted_pipeline=sum((c.weighted_pipeline for c in cells), Decimal(0)),
    )
