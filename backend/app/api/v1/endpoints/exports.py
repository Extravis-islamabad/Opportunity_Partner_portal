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
from app.core.deps import (
    get_admin_scope,
    get_partner_pipeline_scope,
    get_current_admin,
    get_current_user,
    is_customer_company_user,
)
from app.core.exceptions import ForbiddenException
from app.models.company import Company
from app.models.customer_license import CustomerLicense
from app.models.deal_registration import DealRegistration
from app.models.opportunity_product import OpportunityProduct
from app.models.opportunity import Opportunity
from app.models.poc import Poc
from app.models.user import User, UserRole
from app.services import poc_service
from app.services.export_service import (
    build_company_pdf,
    build_company_xlsx,
    build_deal_pdf,
    build_deal_xlsx,
    build_license_pdf,
    build_license_xlsx,
    build_opportunity_pdf,
    build_opportunity_xlsx,
    build_poc_pdf,
    build_poc_xlsx,
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
    product: Optional[str] = None,
    industry: Optional[str] = None,
    time_frame: Optional[str] = None,
) -> list[Opportunity]:
    query = (
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
        )
        .where(Opportunity.deleted_at.is_(None))
    )

    # Partners export what they can read: their own company, plus any
    # resellers underneath them. Matches the opportunity list exactly — an
    # export must never be a way to see more than the UI shows.
    if current_user.role == UserRole.PARTNER:
        query = query.where(
            Opportunity.company_id.in_(
                await get_partner_pipeline_scope(db, current_user)
            )
        )
        if company_id:
            query = query.where(Opportunity.company_id == company_id)
    # Sales reps are scoped to the opportunities assigned to them.
    elif current_user.role == UserRole.SALES_REP:
        query = query.where(Opportunity.sales_rep_id == current_user.id)
    else:
        # Channel-manager admins are scoped to the companies they manage.
        # `scope is None` means superadmin (global); an empty list means the
        # admin manages nothing and must export nothing — hence the explicit
        # `is not None` rather than a truthiness test.
        scope = await get_admin_scope(db, current_user)
        if scope is not None:
            query = query.where(Opportunity.company_id.in_(scope))
        if company_id:
            query = query.where(Opportunity.company_id == company_id)

    if status:
        query = query.where(Opportunity.status == status)
    if country:
        query = query.where(Opportunity.country == country)
    if region:
        query = query.where(Opportunity.region == region)
    # Mirrors the list filters, so an export matches what is on screen.
    if product:
        # Mirrors the list filter: a deal now carries several products, so ask
        # whether any of its lines is this one.
        query = query.where(Opportunity.id.in_(
            select(OpportunityProduct.opportunity_id).where(
                OpportunityProduct.product == product
            )
        ))
    if industry:
        query = query.where(Opportunity.industry == industry)
    if time_frame:
        query = query.where(Opportunity.time_frame == time_frame)
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
        # A customer company takes no part in deal registration, so the export
        # is denied outright rather than returning an empty file — matching
        # the deal list, which denies them too.
        if is_customer_company_user(current_user):
            raise ForbiddenException(
                code="CUSTOMER_COMPANY_FORBIDDEN",
                message="Customer companies cannot export deal registrations",
            )
        # Match the deal *list* (dashboard.list_deals): a partner's own
        # company, and never down the reseller tree — deals carry exclusivity
        # and commission, which stay inside the company that registered them.
        # A partner with no company exports nothing, not everything.
        query = query.where(
            DealRegistration.company_id.in_(
                [current_user.company_id] if current_user.company_id else []
            )
        )
    elif current_user.role == UserRole.SALES_REP:
        # Deal registrations are a partner/admin concern; reps have no scope
        # here, so deny outright rather than fall through to "see everything".
        raise ForbiddenException(message="Sales reps cannot export deal registrations")
    else:
        # Channel-manager admins are scoped to their managed companies.
        scope = await get_admin_scope(db, current_user)
        if scope is not None:
            query = query.where(DealRegistration.company_id.in_(scope))
        if company_id:
            query = query.where(DealRegistration.company_id == company_id)

    if status:
        query = query.where(DealRegistration.status == status)

    query = query.order_by(DealRegistration.created_at.desc()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    return list(result.unique().scalars().all())


async def _fetch_companies(
    db: AsyncSession,
    *,
    admin: User,
    country: Optional[str],
    region: Optional[str],
    search: Optional[str],
    status: Optional[str],
    company_type: Optional[str],
) -> list[Company]:
    query = (
        select(Company)
        .options(
            joinedload(Company.channel_manager),
            # The export carries a Parent Distributor column; without this the
            # row builder would lazy-load outside the greenlet and fail.
            joinedload(Company.parent_distributor),
        )
        .where(Company.deleted_at.is_(None))
    )

    # Channel-manager admins export only companies they manage; superadmins
    # (scope is None) export all. This mirrors the companies list route.
    scope = await get_admin_scope(db, admin)
    if scope is not None:
        query = query.where(Company.id.in_(scope))

    if country:
        query = query.where(Company.country == country)
    if region:
        query = query.where(Company.region == region)
    if search:
        query = query.where(Company.name.ilike(f"%{search}%"))
    if status:
        query = query.where(Company.status == status)
    if company_type:
        query = query.where(Company.company_type == company_type)

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
    product: Optional[str] = None,
    industry: Optional[str] = None,
    time_frame: Optional[str] = None,
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
        product=product,
        industry=industry,
        time_frame=time_frame,
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
    product: Optional[str] = None,
    industry: Optional[str] = None,
    time_frame: Optional[str] = None,
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
        product=product,
        industry=industry,
        time_frame=time_frame,
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
    company_type: Optional[str] = Query(None, pattern="^(customer|distributor|partner)$"),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    companies = await _fetch_companies(
        db, admin=admin, country=country, region=region, search=search, status=status,
        company_type=company_type,
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
    company_type: Optional[str] = Query(None, pattern="^(customer|distributor|partner)$"),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    companies = await _fetch_companies(
        db, admin=admin, country=country, region=region, search=search, status=status,
        company_type=company_type,
    )
    xlsx_bytes = build_company_xlsx(companies)
    return _stream(
        xlsx_bytes,
        "companies.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------ POCs -----------------------------------------

async def _fetch_pocs(
    db: AsyncSession,
    *,
    current_user: User,
    status: Optional[str],
    country: Optional[str],
    search: Optional[str],
) -> list[Poc]:
    query = (
        select(Poc)
        .options(
            joinedload(Poc.opportunity).joinedload(Opportunity.company),
            joinedload(Poc.opportunity).joinedload(Opportunity.sales_rep),
            joinedload(Poc.closed_by_user),
        )
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(Poc.deleted_at.is_(None), Opportunity.deleted_at.is_(None))
    )

    # Same scoping as the POC list (pocs._list_scope): partners by company
    # plus resellers underneath them, sales reps by assignment,
    # channel-manager admins by managed companies.
    if current_user.role == UserRole.PARTNER:
        query = query.where(
            Opportunity.company_id.in_(
                await get_partner_pipeline_scope(db, current_user)
            )
        )
    elif current_user.role == UserRole.SALES_REP:
        query = query.where(Opportunity.sales_rep_id == current_user.id)
    else:
        scope = await get_admin_scope(db, current_user)
        if scope is not None:
            query = query.where(Opportunity.company_id.in_(scope))

    if status:
        query = query.where(Poc.status == status)
    if country:
        query = query.where(Opportunity.country == country)
    if search:
        query = query.where(Opportunity.customer_name.ilike(f"%{search}%"))

    query = query.order_by(Poc.start_date.desc().nullslast()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    return list(result.unique().scalars().all())


def _poc_subtitle(status, country, count) -> str:
    parts = []
    if status:
        parts.append(f"status={status}")
    if country:
        parts.append(f"country={country}")
    return " · ".join(parts) if parts else f"{count} rows"


@router.get("/pocs.pdf")
async def export_pocs_pdf(
    status: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    pocs = await _fetch_pocs(db, current_user=current_user, status=status, country=country, search=search)
    pdf_bytes = build_poc_pdf(pocs, subtitle=_poc_subtitle(status, country, len(pocs)))
    return _stream(pdf_bytes, "pocs.pdf", "application/pdf")


@router.get("/pocs.xlsx")
async def export_pocs_xlsx(
    status: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    pocs = await _fetch_pocs(db, current_user=current_user, status=status, country=country, search=search)
    xlsx_bytes = build_poc_xlsx(pocs)
    return _stream(
        xlsx_bytes,
        "pocs.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------ Licences (post-PO) ---------------------------

async def _fetch_licenses(
    db: AsyncSession,
    *,
    current_user: User,
    status: Optional[str],
    search: Optional[str],
) -> list[tuple]:
    """Returns (CustomerLicense, derived_status_str) tuples.

    Status is derived per row via poc_service.derive_license_status — the
    stored column is a stale cache. When the caller filters by status we
    filter on the derived value, not the column, for the same reason.
    """
    query = (
        select(CustomerLicense)
        .options(joinedload(CustomerLicense.opportunity).joinedload(Opportunity.company))
        .join(Opportunity, CustomerLicense.opportunity_id == Opportunity.id)
        .where(CustomerLicense.deleted_at.is_(None), Opportunity.deleted_at.is_(None))
    )

    # Mirrors the licence list, which shares pocs._list_scope.
    if current_user.role == UserRole.PARTNER:
        query = query.where(
            Opportunity.company_id.in_(
                await get_partner_pipeline_scope(db, current_user)
            )
        )
    elif current_user.role == UserRole.SALES_REP:
        query = query.where(Opportunity.sales_rep_id == current_user.id)
    else:
        scope = await get_admin_scope(db, current_user)
        if scope is not None:
            query = query.where(Opportunity.company_id.in_(scope))

    if search:
        query = query.where(Opportunity.customer_name.ilike(f"%{search}%"))
    if status:
        query = query.where(poc_service.license_status_expr() == status)

    query = query.order_by(CustomerLicense.license_expires_at.asc().nullslast()).limit(EXPORT_ROW_CAP)
    result = await db.execute(query)
    licences = result.unique().scalars().all()
    return [(lic, poc_service.derive_license_status(lic).value) for lic in licences]


@router.get("/licenses.pdf")
async def export_licenses_pdf(
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    rows = await _fetch_licenses(db, current_user=current_user, status=status, search=search)
    subtitle = f"status={status}" if status else f"{len(rows)} rows"
    pdf_bytes = build_license_pdf(rows, subtitle=subtitle)
    return _stream(pdf_bytes, "licenses.pdf", "application/pdf")


@router.get("/licenses.xlsx")
async def export_licenses_xlsx(
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    rows = await _fetch_licenses(db, current_user=current_user, status=status, search=search)
    xlsx_bytes = build_license_xlsx(rows)
    return _stream(
        xlsx_bytes,
        "licenses.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
