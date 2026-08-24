from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_superadmin, assert_manages_company
from app.core.exceptions import ForbiddenException
from app.models.user import User
from app.schemas.company import (
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
    CompanyDetailResponse,
)
from app.schemas.common import MessageResponse
from app.services import company_service

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreateRequest,
    # Superadmin-only: the UI only offers company creation to superadmins
    # (channel managers work within their assigned companies), so the API
    # must enforce the same boundary.
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    return await company_service.create_company(db, data, admin)


@router.get("", status_code=200)
async def list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    country: Optional[str] = None,
    region: Optional[str] = None,
    channel_manager_id: Optional[int] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    company_type: Optional[str] = Query(None, pattern="^(customer|distributor|partner)$"),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Channel-manager scope: a non-superadmin admin only sees companies
    # they channel-manage, regardless of what the client requested.
    if not admin.is_superadmin:
        channel_manager_id = admin.id

    items, total = await company_service.get_companies(
        db, page, page_size, country, region, channel_manager_id, search, status,
        company_type=company_type,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{company_id}", response_model=CompanyDetailResponse, status_code=200)
async def get_company(
    company_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await assert_manages_company(db, admin, company_id, action="view")
    return await company_service.get_company_detail(db, company_id)


@router.put("/{company_id}", response_model=CompanyResponse, status_code=200)
async def update_company(
    company_id: int,
    data: CompanyUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Same scope check the GET has. Without it a channel manager could PUT a
    # company they don't manage and set channel_manager_id to themselves,
    # widening their own scope across every scoped route.
    await assert_manages_company(db, admin, company_id, action="edit")

    # Reassigning a company to a different channel manager is a superadmin
    # action. A channel manager editing their own company must not be able to
    # hand it to someone else — or take another one.
    if not admin.is_superadmin and data.channel_manager_id is not None:
        raise ForbiddenException(
            message="Only superadmins can change a company's channel manager"
        )

    # Company type decides whether that company's users reach deal
    # registration, commissions and scorecards at all, so re-classifying is a
    # superadmin action too — a channel manager must not be able to turn one
    # of their customers into a partner and open those modules up.
    if not admin.is_superadmin and data.company_type is not None:
        raise ForbiddenException(
            message="Only superadmins can change a company's type"
        )

    return await company_service.update_company(db, company_id, data, admin)


@router.delete("/{company_id}", response_model=MessageResponse, status_code=200)
async def deactivate_company(
    company_id: int,
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    await company_service.deactivate_company(db, company_id, admin)
    return MessageResponse(message="Company deactivated successfully")
