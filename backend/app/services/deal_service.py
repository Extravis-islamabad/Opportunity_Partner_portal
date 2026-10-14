from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional
import structlog

from app.models.deal_registration import DealRegistration, DealStatus
from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.dashboard import (
    DealRegistrationCreateRequest,
    DealRegistrationResponse,
    DealApproveRequest,
    DealRejectRequest,
)
from app.core.exceptions import NotFoundException, BadRequestException, ConflictException
from app.utils.audit import write_audit_log
from app.services import currency_service, legal_service
from app.core.deps import assert_manages_company, get_channel_manager_ids
from app.services.notification_service import notify_all_admins, notify_user

logger = structlog.get_logger()


def to_deal_response(
    deal: DealRegistration,
    *,
    company_name: Optional[str] = None,
    registered_by_name: Optional[str] = None,
    extension_pending: bool = False,
) -> DealRegistrationResponse:
    """One place that turns a registration into its API shape.

    Four separate hand-built constructions is how a field ends up on the list
    but not on the approval response — which is exactly what happened to the
    exclusivity dates before this existed. `company_name` and
    `registered_by_name` are overridable because create_deal_registration
    already has both loaded and re-reading them would be a wasted query.
    """
    days_left = None
    if deal.exclusivity_end and deal.status == DealStatus.APPROVED:
        days_left = (deal.exclusivity_end - date.today()).days

    return DealRegistrationResponse(
        id=deal.id,
        company_id=deal.company_id,
        company_name=company_name if company_name is not None else (deal.company.name if deal.company else None),
        registered_by=deal.registered_by,
        registered_by_name=(
            registered_by_name
            if registered_by_name is not None
            else (deal.registered_by_user.full_name if deal.registered_by_user else None)
        ),
        customer_name=deal.customer_name,
        deal_description=deal.deal_description,
        estimated_value=deal.estimated_value,
        currency=deal.currency.value,
        estimated_value_usd=currency_service.reporting_value(
            deal.estimated_value, deal.exchange_rate_to_usd
        ),
        expected_close_date=str(deal.expected_close_date),
        status=deal.status.value,
        exclusivity_start=str(deal.exclusivity_start) if deal.exclusivity_start else None,
        exclusivity_end=str(deal.exclusivity_end) if deal.exclusivity_end else None,
        days_left=days_left,
        expired_at=deal.expired_at,
        extension_pending=extension_pending,
        rejection_reason=deal.rejection_reason,
        client_email=deal.client_email,
        client_website=deal.client_website,
        client_contact=deal.client_contact,
        client_fax=deal.client_fax,
        client_address=deal.client_address,
        individual_name=deal.individual_name,
        individual_department=deal.individual_department,
        individual_designation=deal.individual_designation,
        opportunity_type=deal.opportunity_type,
        opportunity_name=deal.opportunity_name,
        tender_number=deal.tender_number,
        tender_submission_date=(
            str(deal.tender_submission_date) if deal.tender_submission_date else None
        ),
        mal_maf_required=deal.mal_maf_required,
        poc_required=deal.poc_required,
        products=deal.products,
    )


def normalise_customer_name(name: str) -> str:
    """Python half of the exclusivity comparison: trimmed, internal runs of
    whitespace collapsed to one space, lower-cased. lower() rather than
    casefold() so it agrees with Postgres' lower() in _normalised_customer."""
    return " ".join(name.split()).lower()


def _normalised_customer(column):
    """SQL half of normalise_customer_name; the two must stay in step."""
    return func.lower(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


async def create_deal_registration(
    db: AsyncSession, data: DealRegistrationCreateRequest, partner_user: User
) -> DealRegistrationResponse:
    if not partner_user.company_id:
        raise BadRequestException(code="NO_COMPANY", message="Partner must belong to a company")

    # A linked opportunity must exist and be the partner's own company's.
    # Unchecked, a missing id failed on the foreign key (a 500) and another
    # company's id was accepted — tying this registration, and the commission
    # that follows its approval, to a deal the partner has no claim on. Own
    # company only, not down the reseller tree: deal registration is
    # deliberately company-wide (see get_deal_registrations' callers). One
    # message for both cases so the error does not confirm another tenant's
    # opportunity ids.
    if data.opportunity_id is not None:
        from app.models.opportunity import Opportunity

        linked = (await db.execute(
            select(Opportunity.id).where(
                Opportunity.id == data.opportunity_id,
                Opportunity.company_id == partner_user.company_id,
                Opportunity.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if linked is None:
            raise BadRequestException(
                code="INVALID_OPPORTUNITY",
                message="The linked opportunity was not found in your company",
            )

    # Check for active exclusivity conflicts. Compared whitespace-collapsed
    # and case-insensitive on both sides: a plain lower() let "Acme  Corp"
    # (two spaces) through while "Acme Corp" held exclusivity.
    today = date.today()
    conflict_result = await db.execute(
        select(DealRegistration.id).where(
            _normalised_customer(DealRegistration.customer_name)
            == normalise_customer_name(data.customer_name),
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.exclusivity_start <= today,
            DealRegistration.exclusivity_end >= today,
            DealRegistration.company_id != partner_user.company_id,
            DealRegistration.deleted_at.is_(None),
        ).limit(1)
    )
    if conflict_result.scalar_one_or_none() is not None:
        raise ConflictException(
            code="EXCLUSIVITY_CONFLICT",
            message="This customer is currently under an active exclusivity agreement with another partner",
        )

    # Product names are validated against the shared catalogue: an unknown
    # name is dropped rather than rejected, so a stale client cannot fail a
    # whole registration over a renamed product.
    from app.models.opportunity_product import PRODUCTS
    products = [p for p in (data.products or []) if p in PRODUCTS] or None

    deal = DealRegistration(
        company_id=partner_user.company_id,
        registered_by=partner_user.id,
        opportunity_id=data.opportunity_id,
        customer_name=data.customer_name,
        deal_description=data.deal_description,
        estimated_value=data.estimated_value,
        expected_close_date=date.fromisoformat(data.expected_close_date),
        client_email=data.client_email,
        client_website=data.client_website,
        client_contact=data.client_contact,
        client_fax=data.client_fax,
        client_address=data.client_address,
        individual_name=data.individual_name,
        individual_department=data.individual_department,
        individual_designation=data.individual_designation,
        opportunity_type=data.opportunity_type,
        opportunity_name=data.opportunity_name,
        tender_number=data.tender_number,
        tender_submission_date=(
            date.fromisoformat(data.tender_submission_date)
            if data.tender_submission_date
            else None
        ),
        mal_maf_required=data.mal_maf_required,
        poc_required=data.poc_required,
        products=products,
    )
    await legal_service.assert_accepted(db, partner_user)
    await currency_service.stamp(db, deal, getattr(data, "currency", None))

    db.add(deal)
    await db.flush()

    await write_audit_log(db, partner_user.id, "CREATE", "deal_registration", deal.id, {
        "customer_name": data.customer_name,
    })

    company_result = await db.execute(select(Company).where(Company.id == partner_user.company_id))
    company = company_result.scalar_one_or_none()
    company_name = company.name if company else "Unknown"

    await _notify_deal_reviewers(
        db, partner_user.company_id, deal.id,
        f"{company_name} has registered a new deal for customer: {data.customer_name}",
    )

    return to_deal_response(
        deal, company_name=company_name, registered_by_name=partner_user.full_name
    )


async def _notify_deal_reviewers(
    db: AsyncSession, company_id: int, deal_id: int, message: str
) -> None:
    """Tell the people who can actually decide a new registration.

    That is every channel manager of the company (primary and additional)
    plus the superadmins — not every admin. Broadcasting to all admins mailed
    channel managers about other managers' partners, deals they cannot
    approve and should not be reading about in their inbox. A set, so someone
    who is both a superadmin and a manager of the company hears once.
    """
    candidates: set[int] = await get_channel_manager_ids(db, company_id)
    candidates.update((await db.execute(
        select(User.id).where(User.is_superadmin.is_(True))
    )).scalars().all())

    # Inactive or deleted accounts are filtered here rather than per source:
    # get_channel_manager_ids reads assignments, which outlive the account.
    recipients: list[int] = []
    if candidates:
        recipients = sorted((await db.execute(
            select(User.id).where(
                User.id.in_(candidates),
                User.role == UserRole.ADMIN,
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )).scalars().all())

    if not recipients:
        # Nobody assigned and no active superadmin: fall back to the old
        # broadcast so a registration can never sit unseen.
        await notify_all_admins(
            db, "deal_registered", "New Deal Registration", message,
            "deal_registration", deal_id,
        )
        return

    for user_id in recipients:
        await notify_user(
            db, user_id, "deal_registered", "New Deal Registration", message,
            "deal_registration", deal_id,
        )


async def _assert_can_decide_deal(
    db: AsyncSession, admin_user: User, deal: DealRegistration, action: str
) -> None:
    """Approving or rejecting is an act on the company's book, not a read.

    Every admin passes get_current_admin, so without this any channel manager
    could approve another manager's partner's registration — and approval is
    what writes customer ownership and calculates commission. Same rule as
    exclusivity_service.decide_extension: superadmin, or a channel manager of
    the deal's company.
    """
    await assert_manages_company(
        db, admin_user, deal.company_id,
        action=f"{action} deal registrations for",
    )


async def get_deal_registrations(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    registered_by: Optional[int] = None,
    scope_company_ids: Optional[list[int]] = None,
) -> tuple[list, int]:
    query = (
        select(DealRegistration)
        .options(
            joinedload(DealRegistration.company),
            joinedload(DealRegistration.registered_by_user),
        )
        .where(DealRegistration.deleted_at.is_(None))
    )
    count_query = select(func.count(DealRegistration.id)).where(DealRegistration.deleted_at.is_(None))

    # Channel-manager scope: restrict to deals belonging to managed companies
    if scope_company_ids is not None:
        query = query.where(DealRegistration.company_id.in_(scope_company_ids))
        count_query = count_query.where(DealRegistration.company_id.in_(scope_company_ids))

    if company_id:
        query = query.where(DealRegistration.company_id == company_id)
        count_query = count_query.where(DealRegistration.company_id == company_id)
    if status:
        query = query.where(DealRegistration.status == status)
        count_query = count_query.where(DealRegistration.status == status)
    if registered_by:
        query = query.where(DealRegistration.registered_by == registered_by)
        count_query = count_query.where(DealRegistration.registered_by == registered_by)

    query = query.order_by(DealRegistration.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    deals = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # One query for the deals with a request already waiting, so the UI can
    # offer "request an extension" only where it would actually be accepted.
    pending_ids: set[int] = set()
    if deals:
        from app.models.deal_extension import DealExtensionRequest, ExtensionStatus

        pending_ids = set((await db.execute(
            select(DealExtensionRequest.deal_id).where(
                DealExtensionRequest.deal_id.in_([d.id for d in deals]),
                DealExtensionRequest.status == ExtensionStatus.PENDING,
            )
        )).scalars().all())

    items = [
        to_deal_response(d, extension_pending=d.id in pending_ids)
        for d in deals
    ]

    return items, total


async def approve_deal(
    db: AsyncSession, deal_id: int, data: DealApproveRequest, admin_user: User
) -> DealRegistrationResponse:
    result = await db.execute(
        select(DealRegistration)
        .options(joinedload(DealRegistration.company), joinedload(DealRegistration.registered_by_user))
        .where(DealRegistration.id == deal_id, DealRegistration.deleted_at.is_(None))
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise NotFoundException(code="DEAL_NOT_FOUND", message="Deal registration not found")

    # Scope before state, so an out-of-scope manager learns nothing about
    # where the deal is in its lifecycle.
    await _assert_can_decide_deal(db, admin_user, deal, "approve")

    if deal.status != DealStatus.PENDING:
        raise BadRequestException(code="DEAL_NOT_PENDING", message="Only pending deals can be approved")

    # DealApproveRequest already bounds this; checked again because the
    # service is also called directly, and a non-positive window would write
    # an end date before its start.
    if not 1 <= data.exclusivity_days <= 3650:
        raise BadRequestException(
            code="INVALID_EXCLUSIVITY_DAYS",
            message="Exclusivity must be between 1 and 3650 days",
        )

    deal.status = DealStatus.APPROVED
    deal.approved_by = admin_user.id
    deal.approved_at = datetime.now(timezone.utc)
    deal.exclusivity_start = date.today()
    deal.exclusivity_end = date.today() + timedelta(days=data.exclusivity_days)

    await db.flush()

    # Register customer ownership so future opportunities for the same
    # customer (in the same country) from a different company are blocked.
    from app.services import duplicate_service
    try:
        await duplicate_service.upsert_ownership_from_deal(db, deal)
    except Exception:
        # Don't fail the approval if ownership write fails — it's secondary
        pass
    await write_audit_log(db, admin_user.id, "UPDATE", "deal_registration", deal.id, {
        "status": "approved", "exclusivity_days": data.exclusivity_days,
    })

    await notify_user(
        db, deal.registered_by, "deal_approved",
        "Deal Registration Approved",
        f"Your deal registration for {deal.customer_name} has been approved with {data.exclusivity_days}-day exclusivity.",
        "deal_registration", deal.id,
    )

    # Auto-calculate commission. Never block the approval if this fails.
    try:
        from app.services import commission_service

        await commission_service.calculate_commission_for_deal(db, deal.id)
    except Exception as exc:
        logger.warning(
            "deal.commission_calculation_failed",
            deal_id=deal.id,
            error=str(exc),
        )

    return to_deal_response(deal)


async def reject_deal(
    db: AsyncSession, deal_id: int, data: DealRejectRequest, admin_user: User
) -> DealRegistrationResponse:
    result = await db.execute(
        select(DealRegistration)
        .options(joinedload(DealRegistration.company), joinedload(DealRegistration.registered_by_user))
        .where(DealRegistration.id == deal_id, DealRegistration.deleted_at.is_(None))
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise NotFoundException(code="DEAL_NOT_FOUND", message="Deal registration not found")

    await _assert_can_decide_deal(db, admin_user, deal, "reject")

    if deal.status != DealStatus.PENDING:
        raise BadRequestException(code="DEAL_NOT_PENDING", message="Only pending deals can be rejected")

    deal.status = DealStatus.REJECTED
    deal.rejection_reason = data.rejection_reason

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "deal_registration", deal.id, {
        "status": "rejected", "reason": data.rejection_reason,
    })

    await notify_user(
        db, deal.registered_by, "deal_rejected",
        "Deal Registration Rejected",
        f"Your deal registration for {deal.customer_name} has been rejected. Reason: {data.rejection_reason}",
        "deal_registration", deal.id,
    )

    return to_deal_response(deal)
