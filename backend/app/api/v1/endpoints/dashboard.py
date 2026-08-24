from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import (
    get_current_user,
    get_current_admin,
    get_current_partner,
    get_admin_scope,
    get_partner_pipeline_scope,
    get_channel_partner,
    get_poc_editor,
    deny_customer_company,
    deny_sales_rep,
)
from app.models.user import User, UserRole
from app.schemas.dashboard import (
    PocSummaryResponse,
    DeploymentAnalyticsResponse,
    CityFunnelResponse,
    DashboardStatsResponse,
    OpportunityStatusBreakdown,
    MonthlyOpportunityData,
    CompanyPerformance,
    PartnerDashboardResponse,
    ChannelManagerDashboardResponse,
    DealRegistrationCreateRequest,
    DealRegistrationResponse,
    DealApproveRequest,
    DealRejectRequest,
    AnalyticsResponse,
    TargetPlanAnalyticsResponse,
)
from app.services import dashboard_service, deal_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/admin/stats", response_model=DashboardStatsResponse, status_code=200)
async def admin_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_admin_dashboard_stats(db, scope_company_ids=scope)


@router.get("/admin/opportunity-breakdown", status_code=200)
async def opportunity_breakdown(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_opportunity_status_breakdown(db, scope_company_ids=scope)


@router.get("/admin/monthly-data", status_code=200)
async def monthly_data(
    months: int = Query(12, ge=1, le=24),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_monthly_opportunity_data(db, months, scope_company_ids=scope)


@router.get("/admin/analytics", response_model=AnalyticsResponse, status_code=200)
async def admin_analytics(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Aggregations for charts: regions, tiers, industries, top companies,
    funnel, and recent activity. One round-trip for all dashboard widgets."""
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_admin_analytics(db, scope_company_ids=scope)


@router.get("/admin/target-plan", response_model=TargetPlanAnalyticsResponse, status_code=200)
async def target_plan_analytics(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """2027 Target Plan analytics: pipeline by product, customer industry,
    stage probability, quarter / time frame, and Extravis sales rep, plus
    weighted-pipeline totals (worth * probability)."""
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_target_plan_analytics(db, scope_company_ids=scope)


async def _poc_scope(db: AsyncSession, user: User) -> dict:
    """POC/deployment scoping by role: sales reps see only the opportunities
    assigned to them; channel-manager admins see their companies; superadmins
    see everything."""
    if user.role == UserRole.SALES_REP:
        return {"sales_rep_id": user.id}
    return {"scope_company_ids": await get_admin_scope(db, user)}


@router.get("/poc-summary", response_model=PocSummaryResponse, status_code=200)
async def poc_summary(
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """POC widgets: status counts, five-stage funnel, per-country split,
    success rate and average duration."""
    return await dashboard_service.get_poc_summary(db, **await _poc_scope(db, user))


@router.get("/deployment", response_model=DeploymentAnalyticsResponse, status_code=200)
async def deployment_analytics(
    months: int = Query(12, ge=1, le=24),
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Deployment tab: POC stage throughput plus post-PO device/node rollout
    and upcoming licence expiries."""
    return await dashboard_service.get_deployment_analytics(
        db, months=months, **await _poc_scope(db, user)
    )


@router.get("/admin/city-funnel", response_model=CityFunnelResponse, status_code=200)
async def city_funnel(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sales-funnel value by city and quarter (Q1–Q4), split by pipeline
    stage. Quarter is parsed out of the opportunity's time_frame."""
    scope = await get_admin_scope(db, admin)
    return await dashboard_service.get_city_funnel(db, scope_company_ids=scope, year=year)


@router.get("/company/{company_id}/performance", response_model=CompanyPerformance, status_code=200)
async def company_performance(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import ForbiddenException
    # A partner sees their own company, and a distributor also sees each
    # reseller underneath it — this card is an opportunity roll-up, so it has
    # to follow the same scope as the opportunity list rather than lag behind
    # it.
    if current_user.role == UserRole.PARTNER:
        if company_id not in await get_partner_pipeline_scope(db, current_user):
            raise ForbiddenException(
                message="You can only view your own company's performance"
            )
    if current_user.role == UserRole.SALES_REP:
        raise ForbiddenException(message="Sales reps do not have access to company performance")
    return await dashboard_service.get_company_performance(db, company_id)


@router.get("/channel-manager", response_model=ChannelManagerDashboardResponse, status_code=200)
async def channel_manager_dashboard(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_channel_manager_dashboard(db, admin.id)


@router.get("/partner/stats", response_model=PartnerDashboardResponse, status_code=200)
async def partner_stats(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_partner_dashboard(db, partner)


@router.get("/partner/timeline", status_code=200)
async def partner_timeline(
    months: int = Query(6, ge=1, le=12),
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_partner_timeline(db, partner, months)


# Deal Registration endpoints
@router.post("/deals", response_model=DealRegistrationResponse, status_code=201)
async def create_deal(
    data: DealRegistrationCreateRequest,
    # get_channel_partner, not get_current_partner: a customer company's users
    # are partners by role but take no part in the partner programme.
    partner: User = Depends(get_channel_partner),
    db: AsyncSession = Depends(get_db),
):
    return await deal_service.create_deal_registration(db, data, partner)


@router.get("/deals", status_code=200)
async def list_deals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    # deny_sales_rep: this handler predates the sales-rep role and branches
    # `if partner … else show-all`; a rep would land in the else and read the
    # whole dataset. The frontend already hides /deals from reps — this makes
    # the API match. deny_customer_company keeps a customer company out for
    # the same reason: it would otherwise fall into the partner branch and
    # list an empty set, implying the module applies to it.
    current_user: User = Depends(deny_sales_rep),
    _no_customer: User = Depends(deny_customer_company),
    db: AsyncSession = Depends(get_db),
):
    registered_by = None
    scope = None
    if current_user.role == UserRole.PARTNER:
        # Company-wide, and deliberately *not* down the reseller tree. Deal
        # registration carries exclusivity and commission, so a distributor
        # must not read its resellers' deals — only their pipeline.
        scope = [current_user.company_id] if current_user.company_id else []
    elif current_user.role == UserRole.SALES_REP:
        # Reps have no scope over deal registrations; deny rather than let
        # them fall through to the unscoped superadmin branch below.
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(message="Sales reps do not have access to deal registrations")
    elif current_user.role == UserRole.ADMIN and not current_user.is_superadmin:
        # Channel manager: scope to deals for their managed companies
        scope = await get_admin_scope(db, current_user)

    items, total = await deal_service.get_deal_registrations(
        db, page, page_size, company_id, status, registered_by, scope_company_ids=scope
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/deals/{deal_id}/approve", response_model=DealRegistrationResponse, status_code=200)
async def approve_deal(
    deal_id: int,
    data: DealApproveRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await deal_service.approve_deal(db, deal_id, data, admin)


@router.post("/deals/{deal_id}/reject", response_model=DealRegistrationResponse, status_code=200)
async def reject_deal(
    deal_id: int,
    data: DealRejectRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await deal_service.reject_deal(db, deal_id, data, admin)
