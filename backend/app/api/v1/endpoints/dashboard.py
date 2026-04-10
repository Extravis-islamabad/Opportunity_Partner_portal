from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin, get_current_partner
from app.models.user import User, UserRole
from app.schemas.dashboard import (
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
)
from app.services import dashboard_service, deal_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/admin/stats", response_model=DashboardStatsResponse, status_code=200)
async def admin_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_admin_dashboard_stats(db)


@router.get("/admin/opportunity-breakdown", status_code=200)
async def opportunity_breakdown(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_opportunity_status_breakdown(db)


@router.get("/admin/monthly-data", status_code=200)
async def monthly_data(
    months: int = Query(12, ge=1, le=24),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_monthly_opportunity_data(db, months)


@router.get("/company/{company_id}/performance", response_model=CompanyPerformance, status_code=200)
async def company_performance(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == UserRole.PARTNER and current_user.company_id != company_id:
        from app.core.exceptions import ForbiddenException
        raise ForbiddenException(message="You can only view your own company performance")
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


# Deal Registration endpoints
@router.post("/deals", response_model=DealRegistrationResponse, status_code=201)
async def create_deal(
    data: DealRegistrationCreateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await deal_service.create_deal_registration(db, data, partner)


@router.get("/deals", status_code=200)
async def list_deals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    registered_by = None
    if current_user.role == UserRole.PARTNER:
        registered_by = current_user.id

    items, total = await deal_service.get_deal_registrations(
        db, page, page_size, company_id, status, registered_by
    )
    return {
        "items": [item.model_dump() for item in items],
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
