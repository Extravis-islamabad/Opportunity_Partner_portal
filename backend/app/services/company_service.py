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
    ResellerBrief,
)
from app.core.exceptions import NotFoundException, ConflictException, BadRequestException
from app.services import handover_service
from app.utils.audit import write_audit_log
from app.services.notification_service import notify_user


async def assert_valid_parent_distributor(
    db: AsyncSession,
    *,
    child_type: CompanyType,
    parent_distributor_id: Optional[int],
    child_company_id: Optional[int] = None,
) -> Optional[Company]:
    """The one place the reseller-hierarchy shape is enforced.

    Returns the parent company it validated (None when there is no parent), so
    callers that need its name for the response don't re-query for it.

    Three rules, and between them they keep the graph two levels deep and
    acyclic without ever needing a cycle walk:

      1. Only a PARTNER may have a parent. A distributor is already the top of
         a tree and a customer is outside the channel entirely.
      2. The parent must be an existing, live DISTRIBUTOR.
      3. A company is not its own parent.

    Because a child is always a PARTNER and a parent is always a DISTRIBUTOR,
    no company can be both, so a cycle is unreachable by construction. Rule 3
    is belt-and-braces for the one case a single row could manage on its own
    (and is mirrored by ck_companies_parent_not_self in migration 014).

    `child_type` is the type the company will have *after* the write, not the
    one it has now — a single PUT can change type and parent together.
    """
    if parent_distributor_id is None:
        return None

    if child_type != CompanyType.PARTNER:
        raise BadRequestException(
            code="INVALID_PARENT_DISTRIBUTOR",
            message="Only a partner company can sit underneath a distributor",
        )

    if child_company_id is not None and parent_distributor_id == child_company_id:
        raise BadRequestException(
            code="INVALID_PARENT_DISTRIBUTOR",
            message="A company cannot be its own parent distributor",
        )

    result = await db.execute(
        select(Company).where(
            Company.id == parent_distributor_id,
            Company.deleted_at.is_(None),
        )
    )
    parent = result.scalar_one_or_none()
    if parent is None:
        raise BadRequestException(
            code="INVALID_PARENT_DISTRIBUTOR",
            message="Parent distributor not found",
        )
    if parent.company_type != CompanyType.DISTRIBUTOR:
        raise BadRequestException(
            code="INVALID_PARENT_DISTRIBUTOR",
            message="The parent company must be of type distributor",
        )
    return parent


async def assert_can_change_type(
    db: AsyncSession, company: Company, new_type: CompanyType
) -> None:
    """Guard the two reclassifications that would strand an existing link.

    A distributor with resellers underneath it cannot stop being a distributor,
    and a partner that reports to one cannot stop being a partner. Either would
    leave a parent_distributor_id pointing somewhere the hierarchy rules forbid,
    which is exactly the state assert_valid_parent_distributor exists to keep
    out. The caller is told to unlink first rather than having rows silently
    rewritten underneath them.
    """
    if new_type == company.company_type:
        return

    if company.company_type == CompanyType.DISTRIBUTOR:
        reseller_count = await db.execute(
            select(func.count(Company.id)).where(
                Company.parent_distributor_id == company.id,
                Company.deleted_at.is_(None),
            )
        )
        if (reseller_count.scalar() or 0) > 0:
            raise ConflictException(
                code="DISTRIBUTOR_HAS_RESELLERS",
                message=(
                    "This distributor has resellers underneath it. Reassign or "
                    "unlink them before changing its type."
                ),
            )

    if company.parent_distributor_id is not None and new_type != CompanyType.PARTNER:
        raise ConflictException(
            code="RESELLER_TYPE_CHANGE",
            message=(
                "This company reports to a parent distributor. Clear its parent "
                "distributor before changing its type."
            ),
        )


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

    company_type = CompanyType(data.company_type)
    parent = await assert_valid_parent_distributor(
        db,
        child_type=company_type,
        parent_distributor_id=data.parent_distributor_id,
    )

    company = Company(
        name=data.name,
        country=data.country,
        region=data.region,
        city=data.city,
        industry=data.industry,
        contact_email=data.contact_email,
        channel_manager_id=data.channel_manager_id,
        company_type=company_type,
        parent_distributor_id=data.parent_distributor_id,
    )
    db.add(company)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "company", company.id, {
        "name": data.name, "company_type": data.company_type,
        "parent_distributor_id": data.parent_distributor_id,
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
        parent_distributor_id=company.parent_distributor_id,
        parent_distributor_name=parent.name if parent else None,
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
        .options(
            joinedload(Company.channel_manager),
            # So the list can show which distributor a reseller belongs to
            # without a query per row.
            joinedload(Company.parent_distributor),
        )
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
            "parent_distributor_id": c.parent_distributor_id,
            "parent_distributor_name": c.parent_distributor.name if c.parent_distributor else None,
            "partner_count": partner_count,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        })

    return items, total


async def get_company_detail(db: AsyncSession, company_id: int) -> CompanyDetailResponse:
    result = await db.execute(
        select(Company)
        .options(
            joinedload(Company.channel_manager),
            joinedload(Company.parent_distributor),
        )
        .where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    partners_result = await db.execute(
        select(User).where(User.company_id == company_id, User.deleted_at.is_(None))
    )
    partners = partners_result.scalars().all()

    # Empty for anything that isn't a distributor, so this is one cheap query
    # rather than a branch.
    resellers_result = await db.execute(
        select(Company)
        .where(
            Company.parent_distributor_id == company_id,
            Company.deleted_at.is_(None),
        )
        .order_by(Company.name)
    )
    resellers = resellers_result.scalars().all()

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
        parent_distributor_id=company.parent_distributor_id,
        parent_distributor_name=company.parent_distributor.name if company.parent_distributor else None,
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
        resellers=[
            ResellerBrief(
                id=r.id,
                name=r.name,
                country=r.country,
                status=r.status.value,
                tier=tier_for(r),
            )
            for r in resellers
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
        await assert_can_change_type(db, company, update_data["company_type"])

    # Validate the hierarchy against the type the company will *have* after
    # this write, not the one it has now — one PUT can set both. Only checked
    # when the parent is actually part of the payload, so an unrelated edit to
    # a reseller doesn't re-validate (and can't fail on) a link it isn't
    # touching.
    if "parent_distributor_id" in update_data:
        await assert_valid_parent_distributor(
            db,
            child_type=update_data.get("company_type", company.company_type),
            parent_distributor_id=update_data["parent_distributor_id"],
            child_company_id=company.id,
        )

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

    parent_name = None
    if company.parent_distributor_id is not None:
        parent_name_result = await db.execute(
            select(Company.name).where(Company.id == company.parent_distributor_id)
        )
        parent_name = parent_name_result.scalar_one_or_none()

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
        parent_distributor_id=company.parent_distributor_id,
        parent_distributor_name=parent_name,
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
        # Same rule as deactivating one person: a partner still holding live
        # work cannot be switched off silently, even as part of closing their
        # company. The whole company deactivation is refused so the caller
        # hands the pipeline over first rather than losing half of it.
        await handover_service.assert_ready_to_deactivate(db, partner)
        partner.status = UserStatus.INACTIVE
        partner.deleted_at = datetime.now(timezone.utc)

    await db.flush()
    await write_audit_log(
        db, admin_user.id, "DELETE", "company", company_id,
        {"name": company.name, "deactivated_partners": len(partners)},
    )
