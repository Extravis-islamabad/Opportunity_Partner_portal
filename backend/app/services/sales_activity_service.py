"""Sales rep daily activity log.

Reps create/edit/delete their own entries; admins read any rep's month.
Everything user-facing is served from get_activity_month — the Mon–Fri grid
the frontend renders is built client-side, this service just returns the
month's entries grouped by day plus totals.
"""
import re
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.opportunity import Opportunity
from app.models.poc import Poc
from app.models.poc_team import POC_TEAM_ROLE_LABELS
from app.models.sales_activity import ACTIVITY_TYPE_LABELS, ActivityType, SalesActivity
from app.models.user import User, UserRole
from app.schemas.sales_activity import (
    ActivityCreateRequest,
    ActivityDay,
    ActivityMonthResponse,
    ActivityResponse,
    ActivityTypeTotal,
    ActivityUpdateRequest,
    PocActivityEntry,
    PocActivityFeed,
    PocActivityPerson,
)
from app.utils.audit import write_audit_log

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_month(month: str) -> tuple[date, date]:
    """'YYYY-MM' → (first day, last day) of that month."""
    m = _MONTH_RE.match(month or "")
    if not m:
        raise BadRequestException(
            code="INVALID_MONTH",
            message="Month must be in YYYY-MM format",
        )
    year, mo = int(m.group(1)), int(m.group(2))
    return date(year, mo, 1), date(year, mo, monthrange(year, mo)[1])


def to_activity_response(a: SalesActivity) -> ActivityResponse:
    return ActivityResponse(
        id=a.id,
        user_id=a.user_id,
        user_name=a.user.full_name if a.user else None,
        activity_date=a.activity_date,
        activity_type=a.activity_type.value,
        activity_type_label=ACTIVITY_TYPE_LABELS[a.activity_type.value],
        customer_name=a.customer_name,
        opportunity_id=a.opportunity_id,
        opportunity_name=a.opportunity.name if a.opportunity else None,
        poc_id=a.poc_id,
        duration_minutes=a.duration_minutes,
        notes=a.notes,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _activity_query():
    return (
        select(SalesActivity)
        .options(
            joinedload(SalesActivity.user),
            joinedload(SalesActivity.opportunity),
        )
        .where(SalesActivity.deleted_at.is_(None))
    )


async def _get_activity_or_404(db: AsyncSession, activity_id: int) -> SalesActivity:
    result = await db.execute(_activity_query().where(SalesActivity.id == activity_id))
    activity = result.unique().scalar_one_or_none()
    if not activity:
        raise NotFoundException(code="ACTIVITY_NOT_FOUND", message="Activity not found")
    return activity


async def _validate_opportunity(db: AsyncSession, opportunity_id: int) -> None:
    result = await db.execute(
        select(Opportunity.id).where(
            Opportunity.id == opportunity_id,
            Opportunity.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise BadRequestException(
            code="INVALID_OPPORTUNITY",
            message="The linked opportunity does not exist",
        )


async def _validate_poc(db: AsyncSession, poc_id: int, user: User) -> None:
    """The POC must exist, and the logger must be able to work on it.

    Existence alone is not enough: without the access check, anyone could
    attach their activity to any POC by id and appear in a work log they have
    nothing to do with — which is exactly the record this feature is supposed
    to make trustworthy.
    """
    from app.core.deps import assert_can_work_on_poc

    result = await db.execute(
        select(Poc)
        .options(joinedload(Poc.opportunity))
        .where(Poc.id == poc_id, Poc.deleted_at.is_(None))
    )
    poc = result.unique().scalar_one_or_none()
    if poc is None:
        raise BadRequestException(
            code="INVALID_POC",
            message="The linked POC does not exist",
        )
    await assert_can_work_on_poc(db, user, poc.opportunity)


def _validate_activity_date(d: date) -> None:
    """The UI only offers past/current weekdays; enforce the same server-side.

    The +1 day of slack tolerates a client whose local calendar is a day
    ahead of the server's.
    """
    if d.weekday() >= 5:
        raise BadRequestException(
            code="INVALID_ACTIVITY_DATE",
            message="Activities can only be logged on weekdays (Monday–Friday)",
        )
    if d > date.today() + timedelta(days=1):
        raise BadRequestException(
            code="INVALID_ACTIVITY_DATE",
            message="Activities cannot be logged for future dates",
        )


async def create_activity(
    db: AsyncSession, data: ActivityCreateRequest, user: User
) -> ActivityResponse:
    _validate_activity_date(data.activity_date)
    if data.opportunity_id is not None:
        await _validate_opportunity(db, data.opportunity_id)
    if data.poc_id is not None:
        await _validate_poc(db, data.poc_id, user)

    activity = SalesActivity(
        user_id=user.id,
        activity_date=data.activity_date,
        activity_type=ActivityType(data.activity_type),
        customer_name=data.customer_name,
        opportunity_id=data.opportunity_id,
        poc_id=data.poc_id,
        duration_minutes=data.duration_minutes,
        notes=data.notes,
    )
    db.add(activity)
    await db.flush()

    await write_audit_log(
        db, user.id, "CREATE", "sales_activity", activity.id,
        {"type": data.activity_type, "date": str(data.activity_date)},
    )
    # Re-read through the eager-loading query so user/opportunity names are
    # populated without triggering async lazy loads during serialisation.
    return to_activity_response(await _get_activity_or_404(db, activity.id))


def _assert_can_modify(activity: SalesActivity, user: User) -> None:
    """Reps modify their own entries; superadmins may modify anyone's.

    A plain (channel-manager) admin is refused with an accurate message —
    previously they fell into the ownership check and got the misleading
    "your own activities" wording.
    """
    if user.is_superadmin:
        return
    if user.role != UserRole.SALES_REP:
        raise ForbiddenException(
            message="Only superadmins can modify sales rep activities"
        )
    if activity.user_id != user.id:
        raise ForbiddenException(message="You can only modify your own activities")


async def update_activity(
    db: AsyncSession, activity_id: int, data: ActivityUpdateRequest, user: User
) -> ActivityResponse:
    activity = await _get_activity_or_404(db, activity_id)
    _assert_can_modify(activity, user)

    update_data = data.model_dump(exclude_unset=True)
    if "activity_date" in update_data and update_data["activity_date"] is not None:
        _validate_activity_date(update_data["activity_date"])
    if "opportunity_id" in update_data and update_data["opportunity_id"] is not None:
        await _validate_opportunity(db, update_data["opportunity_id"])
    if "poc_id" in update_data and update_data["poc_id"] is not None:
        # Re-checked against the *editor*, not the original logger: a
        # superadmin correcting an entry still may not file it under a POC
        # they have no business in.
        await _validate_poc(db, update_data["poc_id"], user)
    if "activity_type" in update_data:
        update_data["activity_type"] = ActivityType(update_data["activity_type"])

    for key, value in update_data.items():
        setattr(activity, key, value)
    await db.flush()

    await write_audit_log(
        db, user.id, "UPDATE", "sales_activity", activity.id,
        {k: str(v) for k, v in update_data.items()},
    )
    return to_activity_response(await _get_activity_or_404(db, activity.id))


async def delete_activity(db: AsyncSession, activity_id: int, user: User) -> None:
    activity = await _get_activity_or_404(db, activity_id)
    # Owner deletes their own mis-entries; superadmin can clean up anything.
    _assert_can_modify(activity, user)

    activity.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await write_audit_log(db, user.id, "DELETE", "sales_activity", activity.id, {})


async def get_activity_month(
    db: AsyncSession, target_user_id: int, month: str, viewer: User
) -> ActivityMonthResponse:
    """One rep's month: entries grouped by day, plus per-type totals.

    Role gating happens at the endpoint (partners never reach here; reps only
    ever get their own id passed in). The per-record rule enforced here: a
    viewer other than the target may only look at *sales rep* logs — without
    it, GET /activities/month?user_id= let any admin resolve arbitrary user
    ids (partners, peer admins) to names.
    """
    first, last = parse_month(month)

    user_result = await db.execute(
        select(User).where(User.id == target_user_id, User.deleted_at.is_(None))
    )
    target = user_result.scalar_one_or_none()
    if not target:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    if target.id != viewer.id and target.role != UserRole.SALES_REP:
        raise ForbiddenException(
            message="Only sales rep activity logs can be viewed"
        )

    result = await db.execute(
        _activity_query()
        .where(
            SalesActivity.user_id == target_user_id,
            SalesActivity.activity_date >= first,
            SalesActivity.activity_date <= last,
        )
        .order_by(SalesActivity.activity_date.asc(), SalesActivity.created_at.asc())
    )
    activities = result.unique().scalars().all()

    days: dict[date, list[ActivityResponse]] = {}
    type_counts: dict[str, int] = {}
    total_duration = 0
    for a in activities:
        days.setdefault(a.activity_date, []).append(to_activity_response(a))
        type_counts[a.activity_type.value] = type_counts.get(a.activity_type.value, 0) + 1
        total_duration += a.duration_minutes or 0

    return ActivityMonthResponse(
        user_id=target.id,
        user_name=target.full_name,
        month=month,
        days=[
            ActivityDay(date=d, weekday=d.weekday(), items=items)
            for d, items in sorted(days.items())
        ],
        totals_by_type=[
            ActivityTypeTotal(
                activity_type=t,
                label=ACTIVITY_TYPE_LABELS[t],
                count=type_counts[t],
            )
            # Iterate the enum so totals come back in a stable, canonical order.
            for t in (e.value for e in ActivityType)
            if t in type_counts
        ],
        total_activities=len(activities),
        total_duration_minutes=total_duration,
    )


async def get_poc_activity_feed(db: AsyncSession, poc: Poc) -> PocActivityFeed:
    """Every activity on this POC, plus a total per person.

    Two ways an activity lands here, OR'd:

      - it names this POC (poc_id) — logged as POC work;
      - it names the opportunity this POC belongs to — logged against the
        deal, which is the same engagement.

    Both are kept because neither alone is the truth. Only counting poc_id
    would show an empty feed for every POC that predates the link, and only
    counting the opportunity would call a contract negotiation POC work. Each
    entry carries `linked_via` so the difference stays visible; the OR cannot
    double-count, since it is one row either way.

    `by_person` lists everyone currently on the team even when they have
    logged nothing — "assigned but has done nothing recorded" is a thing this
    view exists to show — followed by anyone else who logged against the POC,
    such as someone since taken off the team.
    """
    result = await db.execute(
        _activity_query()
        .where(
            or_(
                SalesActivity.poc_id == poc.id,
                SalesActivity.opportunity_id == poc.opportunity_id,
            )
        )
        .order_by(
            SalesActivity.activity_date.desc(), SalesActivity.created_at.desc()
        )
    )
    activities = list(result.unique().scalars().all())

    items: list[PocActivityEntry] = []
    tallies: dict[int, dict] = {}
    for a in activities:
        items.append(
            PocActivityEntry(
                **to_activity_response(a).model_dump(),
                linked_via="poc" if a.poc_id == poc.id else "opportunity",
            )
        )
        tally = tallies.setdefault(
            a.user_id,
            {"name": a.user.full_name if a.user else None, "count": 0, "minutes": 0},
        )
        tally["count"] += 1
        tally["minutes"] += a.duration_minutes or 0

    # Team first, in roster order, so the view reads as "here is the team and
    # what each of them has done" rather than as a list of whoever happened to
    # log something.
    by_person: list[PocActivityPerson] = []
    seen: set[int] = set()
    for member in sorted(
        (m for m in poc.team_members if m.removed_at is None),
        key=lambda m: m.assigned_at,
    ):
        tally = tallies.get(member.user_id)
        seen.add(member.user_id)
        by_person.append(
            PocActivityPerson(
                user_id=member.user_id,
                user_name=member.user.full_name if member.user else None,
                poc_role=member.role.value,
                poc_role_label=POC_TEAM_ROLE_LABELS[member.role],
                on_team=True,
                activity_count=tally["count"] if tally else 0,
                total_duration_minutes=tally["minutes"] if tally else 0,
            )
        )

    for user_id, tally in tallies.items():
        if user_id in seen:
            continue
        by_person.append(
            PocActivityPerson(
                user_id=user_id,
                user_name=tally["name"],
                on_team=False,
                activity_count=tally["count"],
                total_duration_minutes=tally["minutes"],
            )
        )

    return PocActivityFeed(
        poc_id=poc.id,
        items=items,
        by_person=by_person,
        total_activities=len(items),
        total_duration_minutes=sum(a.duration_minutes or 0 for a in activities),
    )
