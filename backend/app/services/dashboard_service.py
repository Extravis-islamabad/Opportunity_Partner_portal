from decimal import Decimal
from datetime import date, timedelta
from sqlalchemy import select, func, case, extract
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
)
from app.models.audit_log import AuditLog


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
