"""Partner tier: one set of rules, in one place.

There were three. `evaluate_tier_upgrade` (10 approved opportunities + 50%
company LMS completion for gold, 20 + 80% for platinum) was the only one that
ever wrote Company.tier. The partner dashboard drew its progress card from
5 opportunities + 3 courses, and the commission scorecard from 5 approved
*deal registrations* — so a partner could read three different "progress to
gold" numbers on three screens, two of which could never move their tier.

The writer's rules won, because tier sets the commission rate (5/8/12%):
adopting either of the display rules would have re-tiered live companies and
changed what partners are paid, whereas keeping this set means nothing moves
and the two wrong screens simply start telling the truth.

Everything about tier now comes from here. Both criteria are measured
company-wide — a tier belongs to the company, not to whoever happens to be
logged in, which is the bug that made the dashboard count only the current
user's completed courses.
"""
from dataclasses import dataclass
from typing import Optional

from app.models.company import PartnerTier

# Ascending. Index in this list is the comparison used for "is this a
# promotion", so order is load-bearing.
TIER_ORDER: tuple[PartnerTier, ...] = (
    PartnerTier.SILVER,
    PartnerTier.GOLD,
    PartnerTier.PLATINUM,
)


@dataclass(frozen=True)
class TierRule:
    """What a company must reach to hold a tier. Both must be met."""

    approved_opportunities: int
    lms_completion_rate: float


# SILVER is absent on purpose: it is the floor, held by every channel company
# with no requirements to meet, so it has nothing to state.
TIER_RULES: dict[PartnerTier, TierRule] = {
    PartnerTier.GOLD: TierRule(approved_opportunities=10, lms_completion_rate=50.0),
    PartnerTier.PLATINUM: TierRule(approved_opportunities=20, lms_completion_rate=80.0),
}


@dataclass(frozen=True)
class TierStanding:
    """A company's position against the rules, computed once and shared by
    every screen that shows tier."""

    current: PartnerTier
    qualifies_for: PartnerTier
    next_tier: Optional[PartnerTier]
    approved_opportunities: int
    lms_completion_rate: float
    # Requirements for `next_tier`; both zero once at platinum.
    opps_required: int
    lms_rate_required: float
    opps_progress_pct: float
    lms_progress_pct: float
    # The single headline number: how far to the next tier, limited by
    # whichever criterion is furthest behind.
    overall_progress_pct: float


def next_tier(current: PartnerTier) -> Optional[PartnerTier]:
    """The tier above this one, or None at the top."""
    idx = TIER_ORDER.index(current)
    return TIER_ORDER[idx + 1] if idx + 1 < len(TIER_ORDER) else None


def is_promotion(current: PartnerTier, candidate: PartnerTier) -> bool:
    return TIER_ORDER.index(candidate) > TIER_ORDER.index(current)


def qualifying_tier(
    approved_opportunities: int, lms_completion_rate: float
) -> PartnerTier:
    """The highest tier these numbers earn, ignoring the tier already held.

    Walks downward so the highest match wins, and so adding a fourth tier is a
    single entry in TIER_RULES rather than another branch.
    """
    for tier in reversed(TIER_ORDER):
        rule = TIER_RULES.get(tier)
        if rule is None:
            return tier  # SILVER — the floor, always qualified for
        if (
            approved_opportunities >= rule.approved_opportunities
            and lms_completion_rate >= rule.lms_completion_rate
        ):
            return tier
    return PartnerTier.SILVER


def _pct(current: float, required: float) -> float:
    """Progress toward a requirement, capped at 100 and floored at 0.

    A requirement of zero is already met — that is the platinum case, where
    there is nothing left to reach.
    """
    if required <= 0:
        return 100.0
    return float(min(100.0, max(0.0, round((current / required) * 100, 1))))


def standing(
    current: PartnerTier,
    approved_opportunities: int,
    lms_completion_rate: float,
) -> TierStanding:
    """Everything a screen needs to talk about a company's tier."""
    target = next_tier(current)
    rule = TIER_RULES.get(target) if target else None

    opps_required = rule.approved_opportunities if rule else 0
    lms_required = rule.lms_completion_rate if rule else 0.0

    opps_pct = _pct(approved_opportunities, opps_required)
    lms_pct = _pct(lms_completion_rate, lms_required)

    return TierStanding(
        current=current,
        qualifies_for=qualifying_tier(approved_opportunities, lms_completion_rate),
        next_tier=target,
        approved_opportunities=approved_opportunities,
        lms_completion_rate=lms_completion_rate,
        opps_required=opps_required,
        lms_rate_required=lms_required,
        opps_progress_pct=opps_pct,
        lms_progress_pct=lms_pct,
        # Both criteria must be met, so the headline is the weaker of the two.
        # Averaging them would show 75% to a company that has done every course
        # and registered nothing.
        overall_progress_pct=min(opps_pct, lms_pct),
    )


# ---------------------------------------------------------------------------
# Measuring a company
# ---------------------------------------------------------------------------
#
# The thresholds above are only half of a tier model. The other half is how
# the two numbers are counted, and that is exactly where the old
# implementations diverged — one counted approved opportunities, another
# counted approved deal registrations, and a third counted one user's finished
# courses instead of the company's completion rate. Both halves live here now,
# so a caller cannot agree on the rules and still measure differently.

async def measure_company(db, company_id: int) -> tuple[int, float]:
    """(approved opportunities, LMS completion rate %) for a company.

    The LMS rate is company-wide: completed enrolments over total enrolments
    across everyone at the company, which is 0.0 when nobody has enrolled in
    anything — nothing completed out of nothing is not 100%.
    """
    from sqlalchemy import func, select

    from app.models.enrollment import Enrollment, EnrollmentStatus
    from app.models.opportunity import ACCEPTED_STATUSES, Opportunity
    from app.models.user import User

    approved = (await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id,
            Opportunity.status.in_(ACCEPTED_STATUSES),
            Opportunity.deleted_at.is_(None),
        )
    )).scalar() or 0

    member_ids = select(User.id).where(
        User.company_id == company_id, User.deleted_at.is_(None)
    )
    total = (await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.user_id.in_(member_ids))
    )).scalar() or 0
    completed = (await db.execute(
        select(func.count(Enrollment.id)).where(
            Enrollment.user_id.in_(member_ids),
            Enrollment.status == EnrollmentStatus.COMPLETED,
        )
    )).scalar() or 0

    rate = round((completed / total) * 100, 1) if total else 0.0
    return approved, rate


async def company_standing(db, company) -> TierStanding:
    """A company's tier standing, measured and judged by the same rules every
    screen uses. This is what the dashboard, the scorecard and the promotion
    check all call."""
    approved, lms_rate = await measure_company(db, company.id)
    return standing(company.tier, approved, lms_rate)


# ---------------------------------------------------------------------------
# Reviewing a company: promotion, grace, demotion
# ---------------------------------------------------------------------------
#
# Tier used to move in one direction. A company that fell below its
# requirements kept the tier — and the commission rate that comes with it —
# indefinitely, so the requirements only ever meant anything on the way up.
#
# Demotion is real but never immediate. Falling short starts a grace period
# and a notification saying by when and by how much; only a company still
# short when that runs out is moved down. Recovering inside the window clears
# it with nothing having happened.


@dataclass(frozen=True)
class TierChange:
    """What a review did, or None when it did nothing.

    `kind` is one of promoted / at_risk / recovered / demoted. The two tiers
    are equal for at_risk and recovered — nothing moved, the standing did.
    """

    kind: str
    from_tier: PartnerTier
    to_tier: PartnerTier
    approved_opportunities: int
    lms_completion_rate: float
    # Only set for at_risk: the day the grace period runs out.
    demote_on: Optional[str] = None


def shortfall_text(approved: int, lms_rate: float, target: PartnerTier) -> str:
    """Plain words for what is missing, for the notification and the history
    row. A partner told "you no longer qualify" and nothing else has to guess
    which half to fix."""
    rule = TIER_RULES.get(target)
    if rule is None:
        return ""
    missing = []
    if approved < rule.approved_opportunities:
        missing.append(
            f"{approved} of {rule.approved_opportunities} approved opportunities"
        )
    if lms_rate < rule.lms_completion_rate:
        missing.append(
            f"{lms_rate}% of {rule.lms_completion_rate}% training completion"
        )
    return " and ".join(missing)


async def review_company(
    db, company_id: int, *, actor_id: int | None = None
) -> Optional[TierChange]:
    """Judge one company against the rules and act on the result.

    The single write path for Company.tier. Called on the events that can move
    the numbers (an opportunity approved or lost, a course completed) and by
    the daily sweep, which is what makes a grace period expire — an event-driven
    call alone would never fire for a company that has simply gone quiet.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.core.config import settings
    from app.models.company import Company
    from app.models.partner_tier import PartnerTierHistory

    company = (await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not company:
        return None

    # Tier belongs to the partner programme. A customer company has no tier,
    # so it is never moved and never gets a history row — guarding the single
    # write path here is what keeps a customer's tier inert.
    if not company.is_channel_partner:
        return None

    approved, lms_rate = await measure_company(db, company_id)
    qualifies = qualifying_tier(approved, lms_rate)
    previous = company.tier

    if is_promotion(previous, qualifies):
        company.tier = qualifies
        company.tier_at_risk_since = None
        db.add(PartnerTierHistory(
            company_id=company_id,
            previous_tier=previous.value,
            new_tier=qualifies.value,
            changed_by=actor_id,
            reason=(
                f"Promoted: {approved} approved opportunities, "
                f"{lms_rate}% training completion"
            ),
        ))
        await db.flush()
        await _notify_company(
            db, company, "tier_promoted", "Partner tier upgraded",
            f"{company.name} has reached {qualifies.value.title()} tier — "
            f"{approved} approved opportunities and {lms_rate}% training "
            f"completion. Your commission rate goes up with it.",
        )
        return TierChange("promoted", previous, qualifies, approved, lms_rate)

    if qualifies == previous:
        # Qualifying again ends any grace period, quietly unless they were
        # actually told they were at risk.
        if company.tier_at_risk_since is not None:
            company.tier_at_risk_since = None
            await db.flush()
            await _notify_company(
                db, company, "tier_recovered", "Partner tier is safe again",
                f"{company.name} meets the {previous.value.title()} tier "
                f"requirements again. Nothing changes.",
            )
            return TierChange("recovered", previous, previous, approved, lms_rate)
        return None

    # Below the tier held. Start the clock, or act on one that has run out.
    grace_days = settings.TIER_GRACE_DAYS
    now = datetime.now(timezone.utc)

    if company.tier_at_risk_since is None:
        company.tier_at_risk_since = now
        await db.flush()
        deadline = (now + timedelta(days=grace_days)).date()
        await _notify_company(
            db, company, "tier_at_risk", "Partner tier at risk",
            f"{company.name} no longer meets the {previous.value.title()} tier "
            f"requirements: {shortfall_text(approved, lms_rate, previous)}. "
            f"If that is still true on {deadline} the tier drops to "
            f"{qualifies.value.title()}, which lowers the commission rate.",
        )
        return TierChange(
            "at_risk", previous, previous, approved, lms_rate, demote_on=str(deadline)
        )

    started = company.tier_at_risk_since
    if started.tzinfo is None:
        # A timestamp written before the column was timezone-aware still comes
        # back naive; treating it as UTC is what every other ageing check here
        # does.
        started = started.replace(tzinfo=timezone.utc)
    if (now - started).days < grace_days:
        return None

    company.tier = qualifies
    company.tier_at_risk_since = None
    db.add(PartnerTierHistory(
        company_id=company_id,
        previous_tier=previous.value,
        new_tier=qualifies.value,
        changed_by=actor_id,
        reason=(
            f"Demoted after {grace_days}-day grace period: "
            f"{shortfall_text(approved, lms_rate, previous)}"
        ),
    ))
    await db.flush()
    await _notify_company(
        db, company, "tier_demoted", "Partner tier lowered",
        f"{company.name} has been moved from {previous.value.title()} to "
        f"{qualifies.value.title()} tier after the {grace_days}-day grace "
        f"period: {shortfall_text(approved, lms_rate, previous)}. Your commission "
        f"rate changes accordingly.",
    )
    return TierChange("demoted", previous, qualifies, approved, lms_rate)


async def _notify_company(db, company, kind: str, title: str, message: str) -> None:
    """Tell the company's people and the channel manager who owns them.

    Everyone at the company rather than one nominated contact: a tier change
    affects what the whole company is paid, and there is no "billing contact"
    concept here to aim at instead.
    """
    from sqlalchemy import select

    from app.models.user import User, UserRole
    from app.services.notification_service import notify_user

    recipients = set((await db.execute(
        select(User.id).where(
            User.company_id == company.id,
            User.role == UserRole.PARTNER,
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )).scalars().all())
    if company.channel_manager_id:
        recipients.add(company.channel_manager_id)

    for user_id in recipients:
        await notify_user(db, user_id, kind, title, message, "company", company.id)


async def sweep_tier_reviews(db) -> dict[str, int]:
    """Review every channel company: promote, warn, or demote.

    The daily half of the model. Event-driven reviews fire when something
    happens; this one fires when nothing does, which is the case a grace
    period exists for.
    """
    from sqlalchemy import select

    from app.models.company import Company, CompanyType

    company_ids = (await db.execute(
        select(Company.id).where(
            Company.deleted_at.is_(None),
            Company.company_type.in_((CompanyType.PARTNER, CompanyType.DISTRIBUTOR)),
        )
    )).scalars().all()

    counts = {"reviewed": len(company_ids), "promoted": 0, "at_risk": 0,
              "recovered": 0, "demoted": 0}
    for company_id in company_ids:
        change = await review_company(db, company_id)
        if change:
            counts[change.kind] += 1
    return counts


async def tier_history(db, company_id: int) -> list[dict]:
    """Every tier change for a company, newest first, with its reason."""
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.models.partner_tier import PartnerTierHistory

    rows = (await db.execute(
        select(PartnerTierHistory)
        .options(joinedload(PartnerTierHistory.changed_by_user))
        .where(PartnerTierHistory.company_id == company_id)
        .order_by(PartnerTierHistory.changed_at.desc())
    )).unique().scalars().all()

    return [
        {
            "id": r.id,
            "previous_tier": r.previous_tier,
            "new_tier": r.new_tier,
            "reason": r.reason,
            "changed_by_name": r.changed_by_user.full_name if r.changed_by_user else None,
            "changed_at": r.changed_at,
            # Derived rather than stored: the tier order is the authority on
            # which direction a change went, and a stored flag could disagree
            # with it after a tier is added.
            "direction": _direction(r.previous_tier, r.new_tier),
        }
        for r in rows
    ]


def _direction(previous: str | None, new: str) -> str:
    """up / down / unchanged for one history row.

    Tolerates a tier string that is no longer in TIER_ORDER — history outlives
    the model, and an unrecognised value should read as "unknown" rather than
    raise on a page that is only reporting the past.
    """
    values = [t.value for t in TIER_ORDER]
    if previous is None:
        return "up"
    if previous not in values or new not in values:
        return "unknown"
    if values.index(new) > values.index(previous):
        return "up"
    if values.index(new) < values.index(previous):
        return "down"
    return "unchanged"
