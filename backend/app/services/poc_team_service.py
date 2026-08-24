"""Managing who is on a POC.

Add, change role, remove — and notify, because being put on a POC is something
a person needs to find out about without being told twice.

Membership grants access (deps.assert_can_work_on_poc), so the two rules
enforced here are access rules, not tidiness:

  - only Extravis staff (admins and sales reps) can be on a team. A partner
    user is on the other side of the deal, and a membership would hand them
    write access to the POC of an opportunity that might not even be theirs.
  - only active accounts. Adding a deactivated user would create a live
    membership that outlives the account.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models.poc import Poc
from app.models.poc_team import POC_TEAM_ROLE_LABELS, PocTeamMember, PocTeamRole
from app.models.user import User, UserRole, UserStatus
from app.schemas.poc_team import PocTeamMemberResponse
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log

# Who may be put on a POC team. Partners are excluded on purpose — see the
# module docstring. Kept as a frozenset so the check reads the same way
# CHANNEL_COMPANY_TYPES does elsewhere in this codebase.
POC_TEAM_ELIGIBLE_ROLES: frozenset[UserRole] = frozenset(
    {UserRole.ADMIN, UserRole.SALES_REP}
)


def to_team_member_response(member: PocTeamMember) -> PocTeamMemberResponse:
    """Requires .user and .assigned_by_user to be eager-loaded — every query
    in this module does so, because a lazy load here would fail outside the
    greenlet context."""
    user = member.user
    return PocTeamMemberResponse(
        id=member.id,
        poc_id=member.poc_id,
        user_id=member.user_id,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        user_role=user.role.value if user else None,
        job_title=user.job_title if user else None,
        role=member.role.value,
        role_label=POC_TEAM_ROLE_LABELS[member.role],
        assigned_by=member.assigned_by,
        assigned_by_name=(
            member.assigned_by_user.full_name if member.assigned_by_user else None
        ),
        assigned_at=member.assigned_at,
        removed_at=member.removed_at,
    )


def _member_query():
    return select(PocTeamMember).options(
        joinedload(PocTeamMember.user),
        joinedload(PocTeamMember.assigned_by_user),
    )


async def get_team(
    db: AsyncSession, poc_id: int, *, include_removed: bool = False
) -> list[PocTeamMemberResponse]:
    """The current roster, or the full history when include_removed is set."""
    query = _member_query().where(PocTeamMember.poc_id == poc_id)
    if not include_removed:
        query = query.where(PocTeamMember.removed_at.is_(None))

    result = await db.execute(query.order_by(PocTeamMember.assigned_at))
    return [to_team_member_response(m) for m in result.unique().scalars().all()]


async def get_teams_for_pocs(
    db: AsyncSession, poc_ids: list[int]
) -> dict[int, list[PocTeamMemberResponse]]:
    """Current rosters for many POCs in one query.

    The POC list would otherwise issue one team query per row. Returns a dict
    keyed by poc_id with no entry for POCs that have nobody on them, so
    callers use .get(id, []).
    """
    if not poc_ids:
        return {}

    result = await db.execute(
        _member_query()
        .where(
            PocTeamMember.poc_id.in_(poc_ids),
            PocTeamMember.removed_at.is_(None),
        )
        .order_by(PocTeamMember.assigned_at)
    )
    teams: dict[int, list[PocTeamMemberResponse]] = {}
    for member in result.unique().scalars().all():
        teams.setdefault(member.poc_id, []).append(to_team_member_response(member))
    return teams


async def _get_poc_or_404(db: AsyncSession, poc_id: int) -> Poc:
    result = await db.execute(
        select(Poc).where(Poc.id == poc_id, Poc.deleted_at.is_(None))
    )
    poc = result.scalar_one_or_none()
    if not poc:
        raise NotFoundException(code="POC_NOT_FOUND", message="POC not found")
    return poc


async def _assert_eligible(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    if user.role not in POC_TEAM_ELIGIBLE_ROLES:
        raise BadRequestException(
            code="INELIGIBLE_TEAM_MEMBER",
            message="Only Extravis admins and sales reps can be added to a POC team",
        )
    if user.status != UserStatus.ACTIVE:
        raise BadRequestException(
            code="INELIGIBLE_TEAM_MEMBER",
            message="Only active accounts can be added to a POC team",
        )
    return user


async def _find_active_membership(
    db: AsyncSession, poc_id: int, user_id: int
) -> Optional[PocTeamMember]:
    result = await db.execute(
        _member_query().where(
            PocTeamMember.poc_id == poc_id,
            PocTeamMember.user_id == user_id,
            PocTeamMember.removed_at.is_(None),
        )
    )
    return result.unique().scalar_one_or_none()


async def _poc_subject(db: AsyncSession, poc: Poc) -> str:
    """A human label for the POC, for notification copy. Falls back to the id
    rather than failing — a notification is not worth a 500."""
    from app.models.opportunity import Opportunity

    result = await db.execute(
        select(Opportunity.customer_name, Opportunity.name).where(
            Opportunity.id == poc.opportunity_id
        )
    )
    row = result.first()
    if not row:
        return f"POC #{poc.id}"
    customer, name = row
    if customer and name:
        # Opportunity names in this system routinely lead with the customer
        # ("Atlas Manufacturing — Deploy a multi-region platform"), so joining
        # the two unconditionally reads as a stutter.
        return name if customer.lower() in name.lower() else f"{customer} — {name}"
    return customer or name or f"POC #{poc.id}"


async def add_member(
    db: AsyncSession,
    poc_id: int,
    user_id: int,
    role: PocTeamRole,
    actor: User,
) -> PocTeamMemberResponse:
    """Put someone on the POC team and tell them about it.

    Re-adding a previously removed person creates a fresh row: the old one
    keeps its removed_at, so the history reads as two spells rather than being
    rewritten. The partial unique index only constrains live rows, which is
    what makes that legal.
    """
    poc = await _get_poc_or_404(db, poc_id)
    user = await _assert_eligible(db, user_id)

    if await _find_active_membership(db, poc_id, user_id) is not None:
        raise ConflictException(
            code="ALREADY_ON_TEAM",
            message=f"{user.full_name} is already on this POC team",
        )

    member = PocTeamMember(
        poc_id=poc_id,
        user_id=user_id,
        role=role,
        assigned_by=actor.id,
    )
    db.add(member)
    await db.flush()

    label = POC_TEAM_ROLE_LABELS[role]
    subject = await _poc_subject(db, poc)
    await notify_user(
        db, user_id, "poc_team_assigned",
        "Assigned to a POC",
        f"{actor.full_name} added you to the POC for {subject} as {label}.",
        "opportunity", poc.opportunity_id,
    )
    await write_audit_log(
        db, actor.id, "CREATE", "poc_team_member", member.id,
        {"poc_id": poc_id, "user_id": user_id, "role": role.value},
    )

    # Re-read through _member_query so .user and .assigned_by_user are
    # explicitly eager-loaded. Reading them off the just-flushed instance
    # happens to work while both rows sit in the identity map, but that is
    # luck: the moment it misses, the lazy load raises MissingGreenlet.
    created = await db.execute(
        _member_query().where(PocTeamMember.id == member.id)
    )
    return to_team_member_response(created.unique().scalar_one())


async def change_role(
    db: AsyncSession,
    poc_id: int,
    user_id: int,
    role: PocTeamRole,
    actor: User,
) -> PocTeamMemberResponse:
    """Change what someone does on the POC, in place.

    Updates the existing row rather than removing and re-adding, so the person
    keeps one continuous spell on the team — they never lost access, and the
    history should not imply they did.
    """
    poc = await _get_poc_or_404(db, poc_id)
    member = await _find_active_membership(db, poc_id, user_id)
    if member is None:
        raise NotFoundException(
            code="NOT_ON_TEAM", message="That user is not on this POC team"
        )

    if member.role == role:
        return to_team_member_response(member)

    previous = member.role
    member.role = role
    await db.flush()

    label = POC_TEAM_ROLE_LABELS[role]
    subject = await _poc_subject(db, poc)
    await notify_user(
        db, user_id, "poc_team_role_changed",
        "Your POC role changed",
        f"{actor.full_name} changed your role on the POC for {subject} to {label}.",
        "opportunity", poc.opportunity_id,
    )
    await write_audit_log(
        db, actor.id, "UPDATE", "poc_team_member", member.id,
        {
            "poc_id": poc_id,
            "user_id": user_id,
            "before": {"role": previous.value},
            "after": {"role": role.value},
        },
    )
    return to_team_member_response(member)


async def remove_member(
    db: AsyncSession, poc_id: int, user_id: int, actor: User
) -> None:
    """Take someone off the team.

    Soft: the row is stamped, not deleted, so the roster keeps its history.
    Access goes immediately, since every check filters on removed_at IS NULL.

    No notification. Being removed from a POC is usually reassignment rather
    than news, and an email saying so lands badly without the context only the
    person doing it has. The audit log records it either way.
    """
    await _get_poc_or_404(db, poc_id)
    member = await _find_active_membership(db, poc_id, user_id)
    if member is None:
        raise NotFoundException(
            code="NOT_ON_TEAM", message="That user is not on this POC team"
        )

    member.removed_at = datetime.now(timezone.utc)
    member.removed_by = actor.id
    await db.flush()

    await write_audit_log(
        db, actor.id, "DELETE", "poc_team_member", member.id,
        {"poc_id": poc_id, "user_id": user_id, "role": member.role.value},
    )


async def get_assignable_users(db: AsyncSession) -> list[dict]:
    """Everyone who could be put on a POC team, for the picker.

    Not scoped by channel-manager territory: a solution architect is an
    Extravis specialist, not a property of the partner's company, and the
    point of the roster is to reach people the opportunity's own assignment
    does not.
    """
    result = await db.execute(
        select(User)
        .where(
            User.role.in_(POC_TEAM_ELIGIBLE_ROLES),
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
        .order_by(User.full_name)
    )
    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role.value,
            "job_title": u.job_title,
        }
        for u in result.scalars().all()
    ]
