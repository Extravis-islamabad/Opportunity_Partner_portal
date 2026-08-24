from datetime import datetime, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.company import Company, CompanyStatus, CompanyType, PartnerTier
from app.models.user import User, UserRole, UserStatus
from app.models.opportunity import Opportunity
from app.schemas.company import (
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
    CompanyDetailResponse,
    PartnerAccountBrief,
)
from app.core.exceptions import NotFoundException, ConflictException, BadRequestException
from app.utils.audit import write_audit_log
from app.services.notification_service import notify_user


def tier_for(company: Company) -> Optional[str]:
    """A company's tier as it should be shown, or None for a customer.

    Partner tier drives commission rates and scorecard progression, neither of
    which a customer takes part in. The column is still NOT NULL in the
    database (so the enum stays simple), so every read path nulls it out here
    rather than leaking a meaningless "silver" onto a customer record.
    """
    return company.tier.value if company.is_channel_partner else None


async def create_company(
    db: AsyncSession, data: CompanyCreateRequest, admin_user: User
) -> CompanyResponse:
    cm_result = await db.execute(
        select(User).where(
            User.id == data.channel_manager_id,
            User.role == UserRole.ADMIN,
            User.deleted_at.is_(None),
        )
    )
    channel_manager = cm_result.scalar_one_or_none()
    if not channel_manager:
        raise BadRequestException(code="INVALID_CHANNEL_MANAGER", message="Channel manager must be an active admin")

    company = Company(
        name=data.name,
        country=data.country,
        region=data.region,
        city=data.city,
        industry=data.industry,
        contact_email=data.contact_email,
        channel_manager_id=data.channel_manager_id,
        company_type=CompanyType(data.company_type),
    )
    db.add(company)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "company", company.id, {
        "name": data.name, "company_type": data.company_type,
    })

    await notify_user(
        db, channel_manager.id, "channel_manager_assigned",
        "Channel Manager Assignment",
        f"You have been assigned as Channel Manager for {company.name}",
        "company", company.id,
    )

    return CompanyResponse(
        id=company.id,
        name=company.name,
        country=company.country,
        region=company.region,
        city=company.city,
        industry=company.industry,
        contact_email=company.contact_email,
        status=company.status.value,
        company_type=company.company_type.value,
        tier=tier_for(company),
        channel_manager_id=company.channel_manager_id,
        channel_manager_name=channel_manager.full_name,
        partner_count=0,
        opportunity_count=0,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


async def get_companies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    country: Optional[str] = None,
    region: Optional[str] = None,
    channel_manager_id: Optional[int] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    company_type: Optional[str] = None,
) -> tuple[list, int]:
    query = (
        select(Company)
        .options(joinedload(Company.channel_manager))
        .where(Company.deleted_at.is_(None))
    )
    count_query = select(func.count(Company.id)).where(Company.deleted_at.is_(None))

    if country:
        query = query.where(Company.country == country)
        count_query = count_query.where(Company.country == country)
    if region:
        query = query.where(Company.region == region)
        count_query = count_query.where(Company.region == region)
    if channel_manager_id:
        query = query.where(Company.channel_manager_id == channel_manager_id)
        count_query = count_query.where(Company.channel_manager_id == channel_manager_id)
    if search:
        search_filter = Company.name.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    if status:
        query = query.where(Company.status == status)
        count_query = count_query.where(Company.status == status)
    if company_type:
        query = query.where(Company.company_type == company_type)
        count_query = count_query.where(Company.company_type == company_type)

    query = query.order_by(Company.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    companies = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for c in companies:
        partner_count_result = await db.execute(
            select(func.count(User.id)).where(
                User.company_id == c.id, User.deleted_at.is_(None)
            )
        )
        partner_count = partner_count_result.scalar() or 0

        items.append({
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "region": c.region,
            "city": c.city,
            "industry": c.industry,
            "contact_email": c.contact_email,
            "status": c.status.value,
            "company_type": c.company_type.value,
            "tier": tier_for(c),
            "channel_manager_id": c.channel_manager_id,
            "channel_manager_name": c.channel_manager.full_name if c.channel_manager else None,
            "partner_count": partner_count,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        })

    return items, total


async def get_company_detail(db: AsyncSession, company_id: int) -> CompanyDetailResponse:
    result = await db.execute(
        select(Company)
        .options(joinedload(Company.channel_manager))
        .where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    partners_result = await db.execute(
        select(User).where(User.company_id == company_id, User.deleted_at.is_(None))
    )
    partners = partners_result.scalars().all()

    partner_count = len(partners)
    opp_count_result = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id, Opportunity.deleted_at.is_(None)
        )
    )
    opp_count = opp_count_result.scalar() or 0

    return CompanyDetailResponse(
        id=company.id,
        name=company.name,
        country=company.country,
        region=company.region,
        city=company.city,
        industry=company.industry,
        contact_email=company.contact_email,
        status=company.status.value,
        company_type=company.company_type.value,
        tier=tier_for(company),
        channel_manager_id=company.channel_manager_id,
        channel_manager_name=company.channel_manager.full_name if company.channel_manager else None,
        partner_count=partner_count,
        opportunity_count=opp_count,
        created_at=company.created_at,
        updated_at=company.updated_at,
        partners=[
            PartnerAccountBrief(
                id=p.id,
                full_name=p.full_name,
                email=p.email,
                status=p.status.value,
                job_title=p.job_title,
                created_at=p.created_at,
            )
            for p in partners
        ],
    )


async def update_company(
    db: AsyncSession, company_id: int, data: CompanyUpdateRequest, admin_user: User
) -> CompanyResponse:
    result = await db.execute(
        select(Company)
        .options(joinedload(Company.channel_manager))
        .where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    old_cm_id = company.channel_manager_id
    update_data = data.model_dump(exclude_unset=True)

    if "channel_manager_id" in update_data:
        cm_result = await db.execute(
            select(User).where(
                User.id == update_data["channel_manager_id"],
                User.role == UserRole.ADMIN,
                User.deleted_at.is_(None),
            )
        )
        if not cm_result.scalar_one_or_none():
            raise BadRequestException(code="INVALID_CHANNEL_MANAGER", message="Channel manager must be an active admin")

    # Coerce to the enum so the assignment below sets a real CompanyType
    # rather than a bare string (which would break company.is_channel_partner
    # for the rest of this request).
    if update_data.get("company_type") is not None:
        update_data["company_type"] = CompanyType(update_data["company_type"])

    before_state = {key: getattr(company, key) for key in update_data}
    # Convert any enum values for serialization
    for key, value in before_state.items():
        if hasattr(value, 'value'):
            before_state[key] = value.value

    for key, value in update_data.items():
        setattr(company, key, value)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "company", company.id, {
        "before": before_state,
        # Unwrap enums (company_type) — the audit payload must stay JSON-safe.
        "after": {k: (v.value if hasattr(v, "value") else v) for k, v in update_data.items()},
    })

    if "channel_manager_id" in update_data and update_data["channel_manager_id"] != old_cm_id:
        await notify_user(
            db, update_data["channel_manager_id"], "channel_manager_assigned",
            "Channel Manager Assignment",
            f"You have been assigned as Channel Manager for {company.name}",
            "company", company.id,
        )

    await db.refresh(company)
    cm = company.channel_manager

    partner_count_result = await db.execute(
        select(func.count(User.id)).where(User.company_id == company.id, User.deleted_at.is_(None))
    )
    partner_count = partner_count_result.scalar() or 0

    return CompanyResponse(
        id=company.id,
        name=company.name,
        country=company.country,
        region=company.region,
        city=company.city,
        industry=company.industry,
        contact_email=company.contact_email,
        status=company.status.value,
        company_type=company.company_type.value,
        tier=tier_for(company),
        channel_manager_id=company.channel_manager_id,
        channel_manager_name=cm.full_name if cm else None,
        partner_count=partner_count,
        opportunity_count=0,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


async def deactivate_company(db: AsyncSession, company_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    company.status = CompanyStatus.INACTIVE
    company.deleted_at = datetime.now(timezone.utc)

    partners_result = await db.execute(
        select(User).where(User.company_id == company_id, User.deleted_at.is_(None))
    )
    partners = partners_result.scalars().all()
    for partner in partners:
        partner.status = UserStatus.INACTIVE
        partner.deleted_at = datetime.now(timezone.utc)

    await db.flush()
    await write_audit_log(
        db, admin_user.id, "DELETE", "company", company_id,
        {"name": company.name, "deactivated_partners": len(partners)},
    )
