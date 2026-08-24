"""The end of a deal registration's exclusivity window.

Approving a registration grants the partner a window during which no other
partner can register or submit an opportunity for the same customer. The
window is enforced by date — duplicate_service compares today against
exclusivity_end — so it stopped protecting anybody the moment it lapsed. What
was missing was everything around that moment:

  - the partner (and the channel manager who owns the relationship) being told
    it is about to end, while there is still time to do something;
  - a way to ask for more time, and for an admin to grant or refuse it;
  - the registration itself reading `expired` rather than `approved` forever.

The sweep runs daily. Warnings are stamped so they are sent once, and cleared
when an extension is granted so the partner is warned again before the new
end date.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.deal_extension import DealExtensionRequest, ExtensionStatus
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.customer_ownership import CustomerOwnership
from app.models.user import User, UserRole
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log


# ---------------------------------------------------------------------------
# Loading and access
# ---------------------------------------------------------------------------

async def get_deal_or_404(db: AsyncSession, deal_id: int) -> DealRegistration:
    deal = (await db.execute(
        select(DealRegistration)
        .options(joinedload(DealRegistration.company))
        .where(DealRegistration.id == deal_id, DealRegistration.deleted_at.is_(None))
    )).unique().scalar_one_or_none()
    if not deal:
        raise NotFoundException(code="DEAL_NOT_FOUND", message="Deal registration not found")
    return deal


async def assert_can_see_deal(db: AsyncSession, user: User, deal: DealRegistration) -> None:
    """Who may read or act on one registration.

    Deliberately company-wide but *not* down the reseller tree, matching the
    list endpoint: a registration carries exclusivity and commission, so a
    distributor must not reach its resellers' deals.
    """
    if user.role == UserRole.PARTNER:
        if user.company_id != deal.company_id:
            raise NotFoundException(
                code="DEAL_NOT_FOUND", message="Deal registration not found"
            )
        return
    if user.role == UserRole.ADMIN:
        if user.is_superadmin:
            return
        from app.core.deps import get_admin_scope

        scope = await get_admin_scope(db, user)
        if scope is not None and deal.company_id not in scope:
            raise ForbiddenException(
                message="This deal registration is not for a company you manage"
            )
        return
    raise ForbiddenException(message="You do not have access to deal registrations")


# ---------------------------------------------------------------------------
# The daily sweep
# ---------------------------------------------------------------------------

async def sweep_exclusivity(db: AsyncSession) -> dict[str, int]:
    """Warn about windows closing, and close the ones that have run out.

    Returns counts so the caller logs something meaningful. Never warns or
    expires the same registration twice.
    """
    today = date.today()
    warning_days = settings.EXCLUSIVITY_WARNING_DAYS

    rows = (await db.execute(
        select(DealRegistration)
        .options(
            joinedload(DealRegistration.company),
            joinedload(DealRegistration.registered_by_user),
        )
        .where(
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.deleted_at.is_(None),
            DealRegistration.exclusivity_end.isnot(None),
        )
    )).unique().scalars().all()

    warned = 0
    expired = 0

    for deal in rows:
        days_left = (deal.exclusivity_end - today).days

        if days_left < 0:
            await _expire(db, deal)
            expired += 1
        elif days_left <= warning_days and deal.expiry_warned_at is None:
            await _warn(db, deal, days_left)
            deal.expiry_warned_at = datetime.now(timezone.utc)
            warned += 1

    if warned or expired:
        await db.flush()

    return {"checked": len(rows), "warned": warned, "expired": expired}


async def _recipients(db: AsyncSession, deal: DealRegistration) -> set[int]:
    """The partner who registered it, and the channel manager who owns the
    relationship. The manager is included because losing exclusivity on a
    customer is their problem too, and they are the one who can extend it."""
    people = {deal.registered_by}
    if deal.company and deal.company.channel_manager_id:
        people.add(deal.company.channel_manager_id)
    return people


async def _warn(db: AsyncSession, deal: DealRegistration, days_left: int) -> None:
    when = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
    for user_id in await _recipients(db, deal):
        await notify_user(
            db, user_id, "exclusivity_expiring",
            "Deal exclusivity is about to end",
            f"Exclusivity on {deal.customer_name} ends {when} "
            f"({deal.exclusivity_end}). Once it lapses another partner can "
            f"register the same customer. Request an extension if you need "
            f"more time.",
            "deal_registration", deal.id,
        )


async def _expire(db: AsyncSession, deal: DealRegistration) -> None:
    deal.status = DealStatus.EXPIRED
    deal.expired_at = datetime.now(timezone.utc)
    # Stamped even when no warning was sent — a window granted for fewer days
    # than the warning period expires without ever having been "about to".
    # Leaving it null would make the row look un-warned forever.
    if deal.expiry_warned_at is None:
        deal.expiry_warned_at = deal.expired_at

    await _release_ownership(db, deal)

    for user_id in await _recipients(db, deal):
        await notify_user(
            db, user_id, "exclusivity_expired",
            "Deal exclusivity has ended",
            f"Exclusivity on {deal.customer_name} ended on {deal.exclusivity_end}. "
            f"Another partner can now register this customer.",
            "deal_registration", deal.id,
        )


async def _release_ownership(db: AsyncSession, deal: DealRegistration) -> None:
    """Deactivate the customer-ownership row this deal created.

    Only when nothing has pushed it further out: ownership is shared, and a
    later registration for the same customer may have extended valid_until
    past this deal's end. Deactivating then would hand the customer away while
    another window is still open. Blocking already ignores rows by date, so
    this is bookkeeping rather than enforcement — but a table that says a
    partner owns a customer they no longer own is a table people misread.
    """
    today = date.today()
    rows = (await db.execute(
        select(CustomerOwnership).where(
            CustomerOwnership.source_deal_id == deal.id,
            CustomerOwnership.is_active.is_(True),
        )
    )).scalars().all()
    for row in rows:
        if row.valid_until is None or row.valid_until <= today:
            row.is_active = False


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------

async def request_extension(
    db: AsyncSession, deal_id: int, partner: User, days: int, reason: str | None
) -> DealExtensionRequest:
    """A partner asking for more time before their window closes."""
    deal = await get_deal_or_404(db, deal_id)
    await assert_can_see_deal(db, partner, deal)

    if deal.status != DealStatus.APPROVED:
        raise BadRequestException(
            code="DEAL_NOT_EXCLUSIVE",
            message=(
                "Only a deal with live exclusivity can be extended. An expired "
                "registration has to be registered again."
            ),
        )

    existing = (await db.execute(
        select(DealExtensionRequest).where(
            DealExtensionRequest.deal_id == deal_id,
            DealExtensionRequest.status == ExtensionStatus.PENDING,
        )
    )).scalar_one_or_none()
    if existing:
        raise ConflictException(
            code="EXTENSION_ALREADY_REQUESTED",
            message="There is already an extension request waiting on a decision",
        )

    req = DealExtensionRequest(
        deal_id=deal_id,
        requested_by=partner.id,
        requested_days=days,
        reason=reason,
        status=ExtensionStatus.PENDING,
    )
    db.add(req)
    await db.flush()

    await write_audit_log(
        db, partner.id, "CREATE", "deal_extension_request", req.id,
        {"deal_id": deal_id, "requested_days": days},
    )

    # The channel manager decides these; superadmins are told for a company
    # with nobody assigned, so a request cannot sit unseen.
    deciders: set[int] = set()
    if deal.company and deal.company.channel_manager_id:
        deciders.add(deal.company.channel_manager_id)
    else:
        deciders.update((await db.execute(
            select(User.id).where(
                User.is_superadmin.is_(True),
                User.status == "active",
                User.deleted_at.is_(None),
            )
        )).scalars().all())

    for user_id in deciders:
        await notify_user(
            db, user_id, "exclusivity_extension_requested",
            "Exclusivity extension requested",
            f"{partner.full_name} asked for {days} more days of exclusivity on "
            f"{deal.customer_name}, which currently ends {deal.exclusivity_end}."
            + (f" Reason: {reason}" if reason else ""),
            "deal_registration", deal.id,
        )

    return req


async def decide_extension(
    db: AsyncSession,
    request_id: int,
    admin: User,
    *,
    approve: bool,
    granted_days: int | None = None,
    note: str | None = None,
) -> DealExtensionRequest:
    """Grant or refuse an extension.

    An approval may grant fewer days than were asked for. The new window runs
    from the current end date rather than from today: deciding late should not
    quietly shorten the protection that was granted.
    """
    req = (await db.execute(
        select(DealExtensionRequest)
        .options(joinedload(DealExtensionRequest.deal))
        .where(DealExtensionRequest.id == request_id)
    )).unique().scalar_one_or_none()
    if not req:
        raise NotFoundException(
            code="EXTENSION_NOT_FOUND", message="Extension request not found"
        )
    if req.status != ExtensionStatus.PENDING:
        raise ConflictException(
            code="EXTENSION_ALREADY_DECIDED",
            message=f"This request was already {req.status.value}",
        )

    deal = await get_deal_or_404(db, req.deal_id)
    await assert_can_see_deal(db, admin, deal)

    req.decided_by = admin.id
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = note

    if approve:
        days = granted_days if granted_days is not None else req.requested_days
        if days <= 0:
            raise BadRequestException(
                code="INVALID_EXTENSION",
                message="An approved extension has to grant at least one day",
            )
        req.status = ExtensionStatus.APPROVED
        req.granted_days = days

        base = deal.exclusivity_end or date.today()
        deal.exclusivity_end = base + timedelta(days=days)
        # The partner deserves a fresh warning before the new end date.
        deal.expiry_warned_at = None
        await db.flush()

        # Ownership expires with the window it came from; without this the
        # block would lapse on the old date while the registration claims the
        # new one.
        from app.services import duplicate_service

        await duplicate_service.upsert_ownership_from_deal(db, deal)
    else:
        req.status = ExtensionStatus.REFUSED

    await db.flush()

    await write_audit_log(
        db, admin.id, "UPDATE", "deal_extension_request", req.id,
        {
            "status": req.status.value,
            "granted_days": req.granted_days,
            "new_exclusivity_end": str(deal.exclusivity_end),
        },
    )

    if approve:
        message = (
            f"Exclusivity on {deal.customer_name} was extended by "
            f"{req.granted_days} days and now ends {deal.exclusivity_end}."
        )
    else:
        message = (
            f"Your request for more exclusivity on {deal.customer_name} was "
            f"refused. It still ends {deal.exclusivity_end}."
        )
    await notify_user(
        db, req.requested_by,
        "exclusivity_extension_approved" if approve else "exclusivity_extension_refused",
        "Exclusivity extension " + ("approved" if approve else "refused"),
        message + (f" Note: {note}" if note else ""),
        "deal_registration", deal.id,
    )

    return req


async def list_extension_requests(
    db: AsyncSession,
    *,
    scope_company_ids: list[int] | None,
    partner_company_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """Extension requests, newest first.

    `scope_company_ids` is None for a superadmin (no restriction) and a list
    for a channel manager — the same None-versus-list convention used
    everywhere else, never truthiness.
    """
    query = (
        select(DealExtensionRequest)
        .options(
            joinedload(DealExtensionRequest.deal).joinedload(DealRegistration.company),
            joinedload(DealExtensionRequest.requester),
            joinedload(DealExtensionRequest.decider),
        )
        .join(DealRegistration, DealExtensionRequest.deal_id == DealRegistration.id)
        .where(DealRegistration.deleted_at.is_(None))
    )
    if scope_company_ids is not None:
        query = query.where(DealRegistration.company_id.in_(scope_company_ids))
    if partner_company_id is not None:
        query = query.where(DealRegistration.company_id == partner_company_id)
    if status:
        query = query.where(DealExtensionRequest.status == status)

    rows = (await db.execute(
        query.order_by(DealExtensionRequest.created_at.desc())
    )).unique().scalars().all()

    return [
        {
            "id": r.id,
            "deal_id": r.deal_id,
            "customer_name": r.deal.customer_name if r.deal else None,
            "company_name": r.deal.company.name if r.deal and r.deal.company else None,
            "requested_by": r.requested_by,
            "requested_by_name": r.requester.full_name if r.requester else None,
            "requested_days": r.requested_days,
            "granted_days": r.granted_days,
            "reason": r.reason,
            "status": r.status.value,
            "decided_by_name": r.decider.full_name if r.decider else None,
            "decided_at": r.decided_at,
            "decision_note": r.decision_note,
            "exclusivity_end": str(r.deal.exclusivity_end) if r.deal and r.deal.exclusivity_end else None,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def expiring_soon(
    db: AsyncSession, *, scope_company_ids: list[int] | None, company_id: int | None = None
) -> list[dict]:
    """Live windows inside the warning period, closest to lapsing first.

    Backs a dashboard panel: the point is that these are otherwise invisible
    until the day they stop protecting anybody.
    """
    today = date.today()
    cutoff = today + timedelta(days=settings.EXCLUSIVITY_WARNING_DAYS)

    query = (
        select(DealRegistration)
        .options(joinedload(DealRegistration.company))
        .where(
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.deleted_at.is_(None),
            DealRegistration.exclusivity_end.isnot(None),
            DealRegistration.exclusivity_end >= today,
            DealRegistration.exclusivity_end <= cutoff,
        )
    )
    if scope_company_ids is not None:
        query = query.where(DealRegistration.company_id.in_(scope_company_ids))
    if company_id is not None:
        query = query.where(DealRegistration.company_id == company_id)

    rows = (await db.execute(
        query.order_by(DealRegistration.exclusivity_end.asc())
    )).unique().scalars().all()

    # One query for the deals that already have a request waiting, so the UI
    # can offer "request an extension" only where it would actually work.
    pending_ids = set()
    if rows:
        pending_ids = set((await db.execute(
            select(DealExtensionRequest.deal_id).where(
                DealExtensionRequest.deal_id.in_([r.id for r in rows]),
                DealExtensionRequest.status == ExtensionStatus.PENDING,
            )
        )).scalars().all())

    return [
        {
            "deal_id": r.id,
            "customer_name": r.customer_name,
            "company_id": r.company_id,
            "company_name": r.company.name if r.company else None,
            "estimated_value": r.estimated_value,
            "exclusivity_end": str(r.exclusivity_end),
            "days_left": (r.exclusivity_end - today).days,
            "extension_pending": r.id in pending_ids,
        }
        for r in rows
    ]
