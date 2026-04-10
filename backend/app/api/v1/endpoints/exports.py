"""
Export endpoints — stream PDF/XLSX files for list pages.

Reuses the same role-gating and filter vocabulary as the matching list
endpoints but returns ALL matching rows (no pagination) with a hard cap so a
hostile caller cannot force a huge export.
"""
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user
from app.models.company import Company
from app.models.deal_registration import DealRegistration
from app.models.opportunity import Opportunity
from app.models.user import User, UserRole
from app.services.export_service import (
    build_company_pdf,
    build_company_xlsx,
    build_deal_pdf,
    build_deal_xlsx,
    build_opportunity_pdf,
    build_opportunity_xlsx,
)

router = APIRouter(prefix="/exports", tags=["Exports"])

EXPORT_ROW_CAP = 5000  # safety limit


def _stream(content: bytes, filename: str, media_type: str) -> StreamingResponse:
    from io import BytesIO

    buf = BytesIO(content)
    buf.seek(0)
    safe_name = quote(filename)
    return StreamingResponse(
        buf,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-store",
        },
    )


async def _fetch_opportunities(
    db: AsyncSession,
    *,
    current_user: User,
    status: Optional[str],
    company_id: Optional[int],
    country: Optional[str],
    region: Optional[str],
    search: Optional[str],
) -> list[Opportunity]:
    query = (
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
        )
        .where(Opportunity.deleted_at.is_(None))
    )

    # Partners are scoped to their own company + their own submissions
    if current_user.role == UserRole.PARTNER:
        query = query.where(
            Opportunity.company_id == current_user.company_id,
            Opportunity.submitted_by == current_user.id,
        )
    elif company_id:
        query = query.where(Opportunity.company_id == company_id)

    if status:
        query = query.where(Opportunity.status == status)
    if country:
        query = query.where(Opportunity.country == country)
    if region:
        query = query.where(Opportunity.region == region)
    if search:
        query = query.where(
            or_(
                Opportunity.name.ilike(f"%{search}%"),
                Opportunity.customer_name.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Opportunity.created_at.desc()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    return list(result.unique().scalars().all())


async def _fetch_deals(
    db: AsyncSession,
    *,
    current_user: User,
    status: Optional[str],
    company_id: Optional[int],
) -> list[DealRegistration]:
    query = (
        select(DealRegistration)
        .options(
            joinedload(DealRegistration.company),
            joinedload(DealRegistration.registered_by_user),
        )
        .where(DealRegistration.deleted_at.is_(None))
    )

    if current_user.role == UserRole.PARTNER:
        query = query.where(DealRegistration.company_id == current_user.company_id)
    elif company_id:
        query = query.where(DealRegistration.company_id == company_id)

    if status:
        query = query.where(DealRegistration.status == status)

    query = query.order_by(DealRegistration.created_at.desc()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    return list(result.unique().scalars().all())


async def _fetch_companies(
    db: AsyncSession,
    *,
    country: Optional[str],
    region: Optional[str],
    search: Optional[str],
    status: Optional[str],
) -> list[Company]:
    query = (
        select(Company)
        .options(joinedload(Company.channel_manager))
        .where(Company.deleted_at.is_(None))
    )

    if country:
        query = query.where(Company.country == country)
    if region:
        query = query.where(Company.region == region)
    if search:
        query = query.where(Company.name.ilike(f"%{search}%"))
    if status:
        query = query.where(Company.status == status)

    query = query.order_by(Company.created_at.desc()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    return list(result.unique().scalars().all())


# ------------------------------ Opportunities --------------------------------

@router.get("/opportunities.pdf")
async def export_opportunities_pdf(
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    opps = await _fetch_opportunities(
        db,
        current_user=current_user,
        status=status,
        company_id=company_id,
        country=country,
        region=region,
        search=search,
    )
    subtitle_parts = []
    if status:
        subtitle_parts.append(f"status={status}")
    if country:
        subtitle_parts.append(f"country={country}")
    if search:
        subtitle_parts.append(f'search="{search}"')
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else f"{len(opps)} rows"

    pdf_bytes = build_opportunity_pdf(opps, subtitle=subtitle)
    return _stream(pdf_bytes, "opportunities.pdf", "application/pdf")


@router.get("/opportunities.xlsx")
async def export_opportunities_xlsx(
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    opps = await _fetch_opportunities(
        db,
        current_user=current_user,
        status=status,
        company_id=company_id,
        country=country,
        region=region,
        search=search,
    )
    xlsx_bytes = build_opportunity_xlsx(opps)
    return _stream(
        xlsx_bytes,
        "opportunities.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------ Deals ----------------------------------------

@router.get("/deals.pdf")
async def export_deals_pdf(
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    deals = await _fetch_deals(
        db, current_user=current_user, status=status, company_id=company_id,
    )
    subtitle = f"{len(deals)} rows" + (f" · status={status}" if status else "")
    pdf_bytes = build_deal_pdf(deals, subtitle=subtitle)
    return _stream(pdf_bytes, "deals.pdf", "application/pdf")


@router.get("/deals.xlsx")
async def export_deals_xlsx(
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    deals = await _fetch_deals(
        db, current_user=current_user, status=status, company_id=company_id,
    )
    xlsx_bytes = build_deal_xlsx(deals)
    return _stream(
        xlsx_bytes,
        "deals.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------ Companies (admin) ----------------------------

@router.get("/companies.pdf")
async def export_companies_pdf(
    status: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    companies = await _fetch_companies(
        db, country=country, region=region, search=search, status=status,
    )
    subtitle_parts = []
    if status:
        subtitle_parts.append(f"status={status}")
    if country:
        subtitle_parts.append(f"country={country}")
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else f"{len(companies)} rows"
    pdf_bytes = build_company_pdf(companies, subtitle=subtitle)
    return _stream(pdf_bytes, "companies.pdf", "application/pdf")


@router.get("/companies.xlsx")
async def export_companies_xlsx(
    status: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    companies = await _fetch_companies(
        db, country=country, region=region, search=search, status=status,
    )
    xlsx_bytes = build_company_xlsx(companies)
    return _stream(
        xlsx_bytes,
        "companies.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
