from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_superadmin
from app.models.user import User
from app.schemas.company import (
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
    CompanyListResponse,
    CompanyDetailResponse,
)
from app.schemas.common import PaginatedResponse, MessageResponse
from app.services import company_service

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreateRequest,
    admin: User = Depends(get_current_admin),
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
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    items, total = await company_service.get_companies(
        db, page, page_size, country, region, channel_manager_id, search, status
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
    return await company_service.get_company_detail(db, company_id)


@router.put("/{company_id}", response_model=CompanyResponse, status_code=200)
async def update_company(
    company_id: int,
    data: CompanyUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await company_service.update_company(db, company_id, data, admin)


@router.delete("/{company_id}", response_model=MessageResponse, status_code=200)
async def deactivate_company(
    company_id: int,
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    await company_service.deactivate_company(db, company_id, admin)
    return MessageResponse(message="Company deactivated successfully")
