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
    from app.models.opportunity import Opportunity, OpportunityStatus
    from app.models.user import User

    approved = (await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.company_id == company_id,
            Opportunity.status == OpportunityStatus.APPROVED,
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
