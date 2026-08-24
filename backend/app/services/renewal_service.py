"""Licences coming up for renewal.

A licence carried an expiry date and a status that read "expiring soon" for
its last two months. That was the whole of renewals: a date on a screen nobody
had a reason to open. Nobody was told, and a renewal raised by hand was an
ordinary new-business opportunity with no link to the licence it replaced, so
"did this customer renew" was not a question the data could answer.

Three things fix that:

  - a daily sweep that tells the partner, their channel manager and the sales
    rep once, far enough ahead to actually work the renewal;
  - creating the renewal *from* the licence, carrying the deployment's details
    forward so nobody retypes them, and linking it back to what it renews;
  - a deal registration alongside it, because that is what earns commission
    here — a renewal that pays nothing is not a renewal anyone will chase.

The commission engine is untouched: the renewal earns exactly what any other
registered deal earns, at the company's tier when it is approved.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.customer_license import CustomerLicense
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.user import User, UserRole
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log


async def _renewals_by_license(
    db: AsyncSession, license_ids: list[int]
) -> dict[int, int]:
    """{licence id: renewal opportunity id} for the licences given.

    An explicit query rather than a relationship on purpose. A licence already
    loaded in this session carries whatever its relationship held when it was
    first loaded, so a renewal created moments ago reads as absent — which is
    exactly the case that decides whether to chase or refuse. One indexed
    lookup is immune to that.
    """
    if not license_ids:
        return {}
    rows = (await db.execute(
        select(Opportunity.renewal_of_license_id, Opportunity.id).where(
            Opportunity.renewal_of_license_id.in_(license_ids),
            Opportunity.deleted_at.is_(None),
        )
    )).all()
    return {license_id: opp_id for license_id, opp_id in rows}


def _renewable_query():
    """Licences with a real expiry date, joined to the opportunity they came
    from so scoping and naming need no second query."""
    return (
        select(CustomerLicense)
        .options(
            joinedload(CustomerLicense.opportunity).joinedload(Opportunity.company),
        )
        .join(Opportunity, CustomerLicense.opportunity_id == Opportunity.id)
        .where(
            CustomerLicense.deleted_at.is_(None),
            CustomerLicense.license_expires_at.isnot(None),
            Opportunity.deleted_at.is_(None),
        )
    )


async def get_license_or_404(db: AsyncSession, license_id: int) -> CustomerLicense:
    lic = (await db.execute(
        _renewable_query().where(CustomerLicense.id == license_id)
    )).unique().scalar_one_or_none()
    if not lic:
        raise NotFoundException(code="LICENSE_NOT_FOUND", message="Licence not found")
    return lic


async def assert_can_renew(db: AsyncSession, user: User, lic: CustomerLicense) -> None:
    """Who may raise a renewal.

    The incumbent partner and the admins who manage them. A renewal creates an
    opportunity *and* a deal registration in the partner's name, so this is the
    same bar as registering a deal, not the wider read scope.
    """
    opp = lic.opportunity
    if opp is None:
        raise NotFoundException(code="LICENSE_NOT_FOUND", message="Licence not found")

    if user.role == UserRole.PARTNER:
        if user.company_id != opp.company_id:
            raise NotFoundException(
                code="LICENSE_NOT_FOUND", message="Licence not found"
            )
        return
    if user.role == UserRole.ADMIN:
        if user.is_superadmin:
            return
        from app.core.deps import get_admin_scope

        scope = await get_admin_scope(db, user)
        if scope is not None and opp.company_id not in scope:
            raise ForbiddenException(
                message="This licence is not for a company you manage"
            )
        return
    raise ForbiddenException(message="Only partners and admins can raise a renewal")


# ---------------------------------------------------------------------------
# The daily sweep
# ---------------------------------------------------------------------------

async def sweep_renewals(db: AsyncSession) -> dict[str, int]:
    """Tell people about licences approaching expiry, once each."""
    today = date.today()
    cutoff = today + timedelta(days=settings.RENEWAL_NOTICE_DAYS)

    rows = (await db.execute(
        _renewable_query().where(
            CustomerLicense.license_expires_at >= today,
            CustomerLicense.license_expires_at <= cutoff,
            CustomerLicense.renewal_notified_at.is_(None),
        )
    )).unique().scalars().all()

    # A licence somebody has already raised a renewal for is not chased: the
    # work is underway and a reminder would only read as a mistake.
    already = await _renewals_by_license(db, [lic.id for lic in rows])

    notified = 0
    for lic in rows:
        if lic.id in already:
            continue
        await _notify(db, lic, (lic.license_expires_at - today).days)
        lic.renewal_notified_at = datetime.now(timezone.utc)
        notified += 1

    if notified:
        await db.flush()
    return {"checked": len(rows), "notified": notified}


async def _notify(db: AsyncSession, lic: CustomerLicense, days_left: int) -> None:
    opp = lic.opportunity
    recipients: set[int] = set()
    if opp.submitted_by:
        recipients.add(opp.submitted_by)
    if opp.sales_rep_id:
        recipients.add(opp.sales_rep_id)
    if opp.company and opp.company.channel_manager_id:
        recipients.add(opp.company.channel_manager_id)

    for user_id in recipients:
        await notify_user(
            db, user_id, "license_renewal_due",
            "A licence is coming up for renewal",
            f"The licence for {opp.customer_name} expires on "
            f"{lic.license_expires_at} — {days_left} days. Raise the renewal "
            f"from the licence so the details carry across and it earns "
            f"commission when it is approved.",
            "opportunity", opp.id,
        )


# ---------------------------------------------------------------------------
# Raising the renewal
# ---------------------------------------------------------------------------

async def create_renewal(
    db: AsyncSession,
    license_id: int,
    actor: User,
    *,
    worth: float | None = None,
    closing_date: date | None = None,
) -> Opportunity:
    """Raise a renewal opportunity, and the deal registration that pays for it.

    Everything carries forward from the deployment being renewed — customer,
    location, product, sizing — because retyping it is how a renewal ends up
    recorded as unrelated new business. `worth` and `closing_date` are the two
    a renewal genuinely re-decides.

    The opportunity starts as a draft owned by whoever originally submitted it,
    not by whoever clicked: the renewal belongs to the partner, and an admin
    raising it on their behalf should not take the deal off them.
    """
    lic = await get_license_or_404(db, license_id)
    await assert_can_renew(db, actor, lic)

    if await _renewals_by_license(db, [lic.id]):
        raise ConflictException(
            code="ALREADY_RENEWED",
            message="A renewal has already been raised for this licence",
        )

    source = lic.opportunity
    expires = lic.license_expires_at

    renewal = Opportunity(
        name=f"{source.name} — renewal",
        customer_name=source.customer_name,
        region=source.region,
        country=source.country,
        city=source.city,
        # The value of a renewal is the licence that is being renewed, which is
        # what the customer actually pays today — not the original deal's
        # worth, which may have included one-off services.
        worth=worth if worth is not None else (lic.po_value or source.worth),
        # Renewals land on the expiry date unless somebody says otherwise: a
        # renewal closing after the licence lapses is a gap in service.
        closing_date=closing_date or expires,
        requirements=f"Renewal of the licence expiring {expires}.",
        industry=source.industry,
        product=source.product,
        time_frame=source.time_frame,
        company_id=source.company_id,
        submitted_by=source.submitted_by,
        sales_rep_id=source.sales_rep_id,
        status=OpportunityStatus.DRAFT,
        renewal_of_license_id=lic.id,
    )
    db.add(renewal)
    await db.flush()

    # Sizing carried in the description rather than as columns: the renewal's
    # own licence record is created when its PO lands, and guessing the numbers
    # now would put figures on a record nobody has agreed yet.
    sizing = []
    if lic.device_count:
        sizing.append(f"{lic.device_count} devices")
    if lic.node_count:
        sizing.append(f"{lic.node_count} nodes")
    if sizing:
        renewal.requirements += " Current deployment: " + ", ".join(sizing) + "."

    # The deal registration is what earns commission here. Creating it with the
    # renewal is the difference between a renewal that pays the partner and one
    # that quietly does not.
    deal = DealRegistration(
        company_id=source.company_id,
        registered_by=source.submitted_by,
        opportunity_id=renewal.id,
        customer_name=source.customer_name,
        deal_description=f"Licence renewal for {source.customer_name}",
        estimated_value=renewal.worth,
        expected_close_date=renewal.closing_date,
        status=DealStatus.PENDING,
    )
    db.add(deal)
    await db.flush()

    await write_audit_log(
        db, actor.id, "CREATE", "opportunity", renewal.id,
        {
            "renewal_of_license_id": lic.id,
            "source_opportunity_id": source.id,
            "deal_registration_id": deal.id,
        },
    )

    recipients = {source.submitted_by}
    if source.sales_rep_id:
        recipients.add(source.sales_rep_id)
    recipients.discard(actor.id)
    for user_id in recipients:
        await notify_user(
            db, user_id, "renewal_created",
            "A renewal has been raised",
            f"{actor.full_name} raised the renewal for {source.customer_name}. "
            f"It is a draft — check the value and closing date, then submit it "
            f"for review. A deal registration was created alongside it so the "
            f"renewal earns commission once approved.",
            "opportunity", renewal.id,
        )

    return renewal


async def upcoming_renewals(
    db: AsyncSession,
    *,
    scope_company_ids: list[int] | None,
    company_id: int | None = None,
    days: int | None = None,
) -> list[dict]:
    """Licences inside the renewal window, soonest first.

    `scope_company_ids` is None for a superadmin (no restriction) and a list
    for a channel manager — never truthiness, so an empty list restricts to
    nothing rather than everything.
    """
    today = date.today()
    horizon = today + timedelta(days=days or settings.RENEWAL_NOTICE_DAYS)

    query = _renewable_query().where(
        CustomerLicense.license_expires_at >= today,
        CustomerLicense.license_expires_at <= horizon,
    )
    if scope_company_ids is not None:
        query = query.where(Opportunity.company_id.in_(scope_company_ids))
    if company_id is not None:
        query = query.where(Opportunity.company_id == company_id)

    rows = (await db.execute(
        query.order_by(CustomerLicense.license_expires_at.asc())
    )).unique().scalars().all()

    renewals = await _renewals_by_license(db, [lic.id for lic in rows])

    return [
        {
            "license_id": lic.id,
            "opportunity_id": lic.opportunity_id,
            "customer_name": lic.opportunity.customer_name,
            "company_id": lic.opportunity.company_id,
            "company_name": lic.opportunity.company.name if lic.opportunity.company else None,
            "product": lic.opportunity.product,
            "po_value": lic.po_value,
            "device_count": lic.device_count,
            "node_count": lic.node_count,
            "expires_at": str(lic.license_expires_at),
            "days_left": (lic.license_expires_at - today).days,
            "renewal_opportunity_id": renewals.get(lic.id),
            "notified_at": lic.renewal_notified_at,
        }
        for lic in rows
    ]
