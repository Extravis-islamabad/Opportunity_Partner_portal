"""Chasing opportunity reviews that have stopped moving.

An admin opening a pending opportunity claims it: the status becomes
under_review and the partner can no longer edit. That is reasonable while
someone is actually reviewing it. It stops being reasonable the moment the
reviewer goes on leave, because nothing else moved the deal on — it sat
locked, unreviewed, with the partner unable to withdraw or amend it and nobody
being told.

Three things fix that, and all of them live here:

  - a reminder to the reviewer once the claim is a few days old;
  - an escalation to the superadmin and the company's channel manager when it
    is older still, because at that point the reviewer is the problem rather
    than the solution;
  - a release, so another admin can take an abandoned claim back.

Reminders and escalations are stamped on the row so the daily sweep sends each
one once. A nag that arrives every morning is a nag nobody reads.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.models.company import Company
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.user import User, UserRole
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log


def _age_days(claimed_at: datetime) -> int:
    """Whole days since the claim. Naive timestamps are treated as UTC — a
    column that is timezone-aware in the model can still come back naive from
    a database written before that was true."""
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - claimed_at).days


async def release_review_claim(
    db: AsyncSession, opp_id: int, actor: User, reason: str | None = None
) -> None:
    """Hand a claimed review back to the queue.

    The opportunity returns to pending_review and loses its reviewer, so
    another admin can pick it up — and the partner can edit again, which
    matters when the deal has been frozen for weeks.

    Deliberately not restricted to the original claimant: the case this exists
    for is a reviewer who is not there to release it themselves. The caller
    has already been scope-checked against the opportunity.
    """
    from app.services import opportunity_service

    opp = await opportunity_service.get_opportunity_or_404(db, opp_id)

    if opp.status != OpportunityStatus.UNDER_REVIEW:
        raise BadRequestException(
            code="NOT_UNDER_REVIEW",
            message="Only an opportunity currently under review can be released",
        )

    previous_reviewer = opp.reviewed_by
    opp.status = OpportunityStatus.PENDING_REVIEW
    opp.reviewed_by = None
    # Clear the whole ageing trail, not just the claim: the next reviewer
    # deserves their own grace period rather than inheriting a clock that is
    # already past the escalation threshold.
    opp.review_claimed_at = None
    opp.review_reminded_at = None
    opp.review_escalated_at = None
    await db.flush()

    await write_audit_log(
        db, actor.id, "UPDATE", "opportunity", opp.id,
        {
            "action": "review_released",
            "previous_reviewer": previous_reviewer,
            "reason": reason,
        },
    )

    # Tell the person whose claim it was, unless they released it themselves.
    if previous_reviewer and previous_reviewer != actor.id:
        await notify_user(
            db, previous_reviewer, "review_released",
            "A review you claimed was released",
            f"{actor.full_name} released your claim on {opp.customer_name} — "
            f"{opp.name} so it can be picked up by someone else."
            + (f" Reason: {reason}" if reason else ""),
            "opportunity", opp.id,
        )


async def sweep_stale_reviews(db: AsyncSession) -> dict[str, int]:
    """One pass over claimed reviews: remind, then escalate.

    Returns counts so the caller can log something meaningful rather than
    "job ran". Never touches an opportunity twice for the same stage.
    """
    reminder_days = settings.REVIEW_REMINDER_DAYS
    escalation_days = settings.REVIEW_ESCALATION_DAYS

    result = await db.execute(
        select(Opportunity)
        .options(joinedload(Opportunity.company), joinedload(Opportunity.submitted_by_user))
        .where(
            Opportunity.status == OpportunityStatus.UNDER_REVIEW,
            Opportunity.deleted_at.is_(None),
            Opportunity.review_claimed_at.isnot(None),
        )
    )
    claimed = result.unique().scalars().all()

    reminded = 0
    escalated = 0

    for opp in claimed:
        age = _age_days(opp.review_claimed_at)
        subject = f"{opp.customer_name} — {opp.name}"

        if age >= escalation_days and opp.review_escalated_at is None:
            await _escalate(db, opp, age, subject)
            opp.review_escalated_at = datetime.now(timezone.utc)
            escalated += 1
        elif age >= reminder_days and opp.review_reminded_at is None:
            if opp.reviewed_by:
                await notify_user(
                    db, opp.reviewed_by, "review_reminder",
                    "A review is waiting on you",
                    f"You claimed {subject} {age} days ago and it is still under "
                    f"review. The partner cannot edit it until you approve or "
                    f"reject it.",
                    "opportunity", opp.id,
                )
            opp.review_reminded_at = datetime.now(timezone.utc)
            reminded += 1

    if reminded or escalated:
        await db.flush()

    return {"claimed": len(claimed), "reminded": reminded, "escalated": escalated}


async def _escalate(db: AsyncSession, opp: Opportunity, age: int, subject: str) -> None:
    """Tell the people who can do something about an abandoned claim.

    The reviewer has already been reminded and has not acted, so escalation
    goes over their head: to the company's channel manager, who owns the
    relationship, and to the superadmins, who can reassign. The reviewer is
    told too — being escalated should not be a surprise.
    """
    recipients: set[int] = set()

    if opp.company and opp.company.channel_manager_id:
        recipients.add(opp.company.channel_manager_id)

    superadmins = (await db.execute(
        select(User.id).where(
            User.is_superadmin.is_(True),
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )).scalars().all()
    recipients.update(superadmins)

    if opp.reviewed_by:
        recipients.add(opp.reviewed_by)

    reviewer_name = "an admin"
    if opp.reviewed_by:
        reviewer = (await db.execute(
            select(User.full_name).where(User.id == opp.reviewed_by)
        )).scalar_one_or_none()
        reviewer_name = reviewer or reviewer_name

    for user_id in recipients:
        await notify_user(
            db, user_id, "review_escalated",
            "A review has been stuck too long",
            f"{subject} has been under review by {reviewer_name} for {age} days "
            f"and the partner still cannot edit it. Release the claim so someone "
            f"else can pick it up, or approve or reject it.",
            "opportunity", opp.id,
        )


async def list_stale_reviews(
    db: AsyncSession, scope_company_ids: list[int] | None
) -> list[dict]:
    """Claimed reviews past the reminder threshold, oldest first.

    Backs an admin queue: the whole point is that these are invisible today
    unless somebody happens to open the right opportunity.
    """
    query = (
        select(Opportunity)
        .options(joinedload(Opportunity.company), joinedload(Opportunity.reviewer))
        .where(
            Opportunity.status == OpportunityStatus.UNDER_REVIEW,
            Opportunity.deleted_at.is_(None),
            Opportunity.review_claimed_at.isnot(None),
        )
    )
    if scope_company_ids is not None:
        query = query.where(Opportunity.company_id.in_(scope_company_ids))

    rows = (await db.execute(
        query.order_by(Opportunity.review_claimed_at.asc())
    )).unique().scalars().all()

    out = []
    for opp in rows:
        age = _age_days(opp.review_claimed_at)
        if age < settings.REVIEW_REMINDER_DAYS:
            continue
        out.append({
            "id": opp.id,
            "name": opp.name,
            "customer_name": opp.customer_name,
            "company_name": opp.company.name if opp.company else None,
            "reviewer_id": opp.reviewed_by,
            "reviewer_name": opp.reviewer.full_name if opp.reviewer else None,
            "claimed_at": opp.review_claimed_at,
            "days_claimed": age,
            "escalated": opp.review_escalated_at is not None,
        })
    return out
