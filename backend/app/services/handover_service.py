"""Handing someone's work over before their account is switched off.

Deactivation used to be a status flag. Everything the person held stayed
pointing at a login nobody can use: opportunities they submitted, deals they
registered, companies they channel-managed, POCs they were staffed on, stages
they owned. None of it disappeared — it became invisible, which is worse. A
review queue owned by a leaver still looks like somebody is on it.

So reassignment is a precondition now, not a tidy-up. `outstanding_work` is
what the account still holds; `deactivate` refuses while that is non-empty;
`hand_over` moves it and records who took what.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models.company import Company
from app.models.deal_registration import DealRegistration
from app.models.handover import UserHandover
from app.models.opportunity import CLOSED_STATUSES, Opportunity, OpportunityStatus
from app.models.poc import POC_STAGE_KEYS, Poc, PocStatus
from app.models.poc_team import PocTeamMember
from app.models.user import User, UserRole, UserStatus
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log

# Work that has stopped moving is not work: a closed deal keeps its original
# submitter as a matter of record, and reassigning it would rewrite history
# rather than hand over a responsibility.
_LIVE_OPPORTUNITY = (
    Opportunity.deleted_at.is_(None),
    Opportunity.status.notin_((*CLOSED_STATUSES, OpportunityStatus.REMOVED)),
)


async def outstanding_work(db: AsyncSession, user: User) -> dict:
    """What this account still holds, by kind.

    Only live things. The counts are what the confirmation screen shows and
    what deactivation checks, so "outstanding" has exactly one definition.
    """
    submitted = (await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.submitted_by == user.id, *_LIVE_OPPORTUNITY
        )
    )).scalar() or 0

    as_rep = (await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.sales_rep_id == user.id, *_LIVE_OPPORTUNITY
        )
    )).scalar() or 0

    companies = (await db.execute(
        select(func.count(Company.id)).where(
            Company.channel_manager_id == user.id, Company.deleted_at.is_(None)
        )
    )).scalar() or 0

    deals = (await db.execute(
        select(func.count(DealRegistration.id)).where(
            DealRegistration.registered_by == user.id,
            DealRegistration.deleted_at.is_(None),
            DealRegistration.status == "pending",
        )
    )).scalar() or 0

    # Team seats on POCs that are still running. A seat on a finished POC is
    # history, and moving it would put somebody on a team they never joined.
    poc_seats = (await db.execute(
        select(func.count(PocTeamMember.id))
        .join(Poc, PocTeamMember.poc_id == Poc.id)
        .where(
            PocTeamMember.user_id == user.id,
            PocTeamMember.removed_at.is_(None),
            Poc.status.in_((PocStatus.NOT_STARTED, PocStatus.RUNNING)),
        )
    )).scalar() or 0

    stage_owner = 0
    running = (await db.execute(
        select(Poc).where(Poc.status.in_((PocStatus.NOT_STARTED, PocStatus.RUNNING)))
    )).scalars().all()
    for poc in running:
        stage_owner += sum(
            1 for key in POC_STAGE_KEYS if poc.owner_id_for(key) == user.id
        )

    counts = {
        "opportunities_submitted": submitted,
        "opportunities_as_sales_rep": as_rep,
        "companies_managed": companies,
        "deal_registrations_pending": deals,
        "poc_team_seats": poc_seats,
        "poc_stages_owned": stage_owner,
    }
    return {
        "counts": counts,
        "total": sum(counts.values()),
    }


def _assert_can_receive(leaver: User, successor: User, work: dict) -> None:
    """Whether this successor can actually hold what is being moved.

    Checked per kind rather than by role alone: the failure this prevents is a
    partner's pipeline landing on an admin account, where the partner-scoped
    queries will never look for it again.
    """
    counts = work["counts"]

    if successor.id == leaver.id:
        raise BadRequestException(
            code="SAME_USER", message="Pick somebody other than the person leaving"
        )
    if successor.status != UserStatus.ACTIVE or successor.deleted_at is not None:
        raise BadRequestException(
            code="SUCCESSOR_INACTIVE",
            message="The person taking over has to have an active account",
        )

    if counts["opportunities_submitted"] or counts["deal_registrations_pending"]:
        if successor.role != UserRole.PARTNER:
            raise BadRequestException(
                code="SUCCESSOR_NOT_PARTNER",
                message=(
                    "Submitted opportunities and deal registrations belong to a "
                    "partner account, so they can only move to another partner"
                ),
            )
        if successor.company_id != leaver.company_id:
            raise BadRequestException(
                code="SUCCESSOR_WRONG_COMPANY",
                message=(
                    "A partner's pipeline can only move to someone at the same "
                    "company — it stays with the company, not the person"
                ),
            )

    if counts["companies_managed"] and successor.role != UserRole.ADMIN:
        raise BadRequestException(
            code="SUCCESSOR_NOT_ADMIN",
            message="Managed companies can only move to another admin",
        )

    internal = (
        counts["opportunities_as_sales_rep"]
        + counts["poc_team_seats"]
        + counts["poc_stages_owned"]
    )
    if internal and successor.role not in (UserRole.ADMIN, UserRole.SALES_REP):
        raise BadRequestException(
            code="SUCCESSOR_NOT_INTERNAL",
            message=(
                "Sales-rep assignments and POC work can only move to an admin "
                "or a sales rep"
            ),
        )


async def hand_over(
    db: AsyncSession,
    leaver: User,
    successor: User,
    actor: User,
    notes: str | None = None,
) -> UserHandover:
    """Move everything the leaver still holds to the successor."""
    work = await outstanding_work(db, leaver)
    if work["total"] == 0:
        raise BadRequestException(
            code="NOTHING_TO_HAND_OVER",
            message=f"{leaver.full_name} has nothing outstanding to hand over",
        )
    _assert_can_receive(leaver, successor, work)

    await db.execute(
        update(Opportunity)
        .where(Opportunity.submitted_by == leaver.id, *_LIVE_OPPORTUNITY)
        .values(submitted_by=successor.id)
    )
    await db.execute(
        update(Opportunity)
        .where(Opportunity.sales_rep_id == leaver.id, *_LIVE_OPPORTUNITY)
        .values(sales_rep_id=successor.id)
    )
    await db.execute(
        update(Company)
        .where(Company.channel_manager_id == leaver.id, Company.deleted_at.is_(None))
        .values(channel_manager_id=successor.id)
    )
    await db.execute(
        update(DealRegistration)
        .where(
            DealRegistration.registered_by == leaver.id,
            DealRegistration.deleted_at.is_(None),
            DealRegistration.status == "pending",
        )
        .values(registered_by=successor.id)
    )

    await _move_poc_work(db, leaver, successor)
    await db.flush()

    record = UserHandover(
        from_user_id=leaver.id,
        to_user_id=successor.id,
        performed_by=actor.id,
        moved=work["counts"],
        notes=notes,
    )
    db.add(record)
    await db.flush()

    await write_audit_log(
        db, actor.id, "UPDATE", "user", leaver.id,
        {
            "action": "handover",
            "to_user_id": successor.id,
            "moved": work["counts"],
        },
    )

    await notify_user(
        db, successor.id, "work_handed_over",
        "Work has been handed over to you",
        f"{leaver.full_name}'s open work has been reassigned to you: "
        + ", ".join(
            f"{count} {kind.replace('_', ' ')}"
            for kind, count in work["counts"].items()
            if count
        )
        + "."
        + (f" Note: {notes}" if notes else ""),
        "user", successor.id,
    )

    return record


async def _move_poc_work(db: AsyncSession, leaver: User, successor: User) -> None:
    """Team seats and stage ownership on POCs that are still running."""
    seats = (await db.execute(
        select(PocTeamMember)
        .join(Poc, PocTeamMember.poc_id == Poc.id)
        .where(
            PocTeamMember.user_id == leaver.id,
            PocTeamMember.removed_at.is_(None),
            Poc.status.in_((PocStatus.NOT_STARTED, PocStatus.RUNNING)),
        )
    )).scalars().all()

    for seat in seats:
        already = (await db.execute(
            select(PocTeamMember).where(
                PocTeamMember.poc_id == seat.poc_id,
                PocTeamMember.user_id == successor.id,
                PocTeamMember.removed_at.is_(None),
            )
        )).scalar_one_or_none()

        if already is not None:
            # The successor is already on this POC. Moving the seat would break
            # the one-active-seat-per-person index, and they cannot hold two
            # roles anyway — so the leaver's seat is closed and the role they
            # already have stands.
            seat.removed_at = datetime.now(timezone.utc)
        else:
            seat.user_id = successor.id

    # Stage ownership follows separately: a stage owner is not always a team
    # member any more (a member can be removed while the column still names
    # them), and the tracker resolves owners against the live roster.
    pocs = (await db.execute(
        select(Poc).where(Poc.status.in_((PocStatus.NOT_STARTED, PocStatus.RUNNING)))
    )).scalars().all()
    for poc in pocs:
        for key in POC_STAGE_KEYS:
            if poc.owner_id_for(key) == leaver.id:
                setattr(poc, f"{key}_owner_id", successor.id)


async def assert_ready_to_deactivate(db: AsyncSession, user: User) -> None:
    """Refuse to switch off an account that still holds live work."""
    work = await outstanding_work(db, user)
    if work["total"] == 0:
        return
    outstanding = ", ".join(
        f"{count} {kind.replace('_', ' ')}"
        for kind, count in work["counts"].items()
        if count
    )
    raise ConflictException(
        code="HANDOVER_REQUIRED",
        message=(
            f"{user.full_name} still holds {outstanding}. Hand that over to "
            f"somebody before deactivating the account — otherwise it stays "
            f"assigned to a login nobody can use."
        ),
    )


async def history(db: AsyncSession, user_id: int) -> list[dict]:
    """Handovers into or out of this account, newest first."""
    from sqlalchemy.orm import joinedload

    rows = (await db.execute(
        select(UserHandover)
        .options(
            joinedload(UserHandover.from_user),
            joinedload(UserHandover.to_user),
            joinedload(UserHandover.performed_by_user),
        )
        .where(
            (UserHandover.from_user_id == user_id)
            | (UserHandover.to_user_id == user_id)
        )
        .order_by(UserHandover.created_at.desc())
    )).unique().scalars().all()

    return [
        {
            "id": r.id,
            "from_user_id": r.from_user_id,
            "from_user_name": r.from_user.full_name if r.from_user else None,
            "to_user_id": r.to_user_id,
            "to_user_name": r.to_user.full_name if r.to_user else None,
            "performed_by_name": (
                r.performed_by_user.full_name if r.performed_by_user else None
            ),
            "moved": r.moved,
            "notes": r.notes,
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def load_successor(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user:
        raise NotFoundException(
            code="USER_NOT_FOUND", message="That person could not be found"
        )
    return user
