"""
Commission service — calculation, listing, scorecard, leaderboard, statements.

Design notes:
- `calculate_commission_for_deal` is idempotent (unique constraint on deal_id)
  and snapshots `tier_at_calculation` + `rate_percentage` so later rate or
  tier changes don't mutate past commissions.
- Failures in calculation must never block deal approval: call sites should
  wrap in try/except + structlog.
- All money math uses Decimal with ROUND_HALF_EVEN quantized to 2 places.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Optional

import structlog
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.commission import (
    Commission,
    CommissionStatement,
    CommissionStatus,
    TierCommissionRate,
)
from app.models.company import Company, PartnerTier
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.user import User, UserRole
from app.schemas.commission import (
    Badge,
    CommissionRead,
    LeaderboardEntry,
    LeaderboardResponse,
    MonthlyCommissionPoint,
    ScorecardRead,
    StatementPeriodSummary,
)
from app.services.notification_service import notify_user
from app.utils.audit import write_audit_log

logger = structlog.get_logger()

CENTS = Decimal("0.01")

# Used to hint at the next tier on the scorecard
TIER_ORDER = [PartnerTier.SILVER, PartnerTier.GOLD, PartnerTier.PLATINUM]
# Number of approved deals required to advance to the given tier
TIER_THRESHOLDS = {
    PartnerTier.GOLD: 5,
    PartnerTier.PLATINUM: 15,
}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_EVEN)


async def _get_active_rate(
    db: AsyncSession, tier: PartnerTier, as_of: Optional[date] = None
) -> Decimal:
    as_of = as_of or date.today()
    result = await db.execute(
        select(TierCommissionRate)
        .where(
            TierCommissionRate.tier == tier,
            TierCommissionRate.effective_from <= as_of,
            or_(
                TierCommissionRate.effective_to.is_(None),
                TierCommissionRate.effective_to >= as_of,
            ),
        )
        .order_by(TierCommissionRate.effective_from.desc())
        .limit(1)
    )
    rate = result.scalar_one_or_none()
    if rate is None:
        # Fallback defaults so the system still works if rates aren't seeded
        defaults = {
            PartnerTier.SILVER: Decimal("5.00"),
            PartnerTier.GOLD: Decimal("8.00"),
            PartnerTier.PLATINUM: Decimal("12.00"),
        }
        return defaults[tier]
    return rate.percentage


def _build_commission_read(c: Commission) -> CommissionRead:
    return CommissionRead(
        id=c.id,
        deal_id=c.deal_id,
        company_id=c.company_id,
        company_name=c.company.name if c.company else None,
        user_id=c.user_id,
        user_name=c.user.full_name if c.user else None,
        tier_at_calculation=c.tier_at_calculation.value,
        rate_percentage=c.rate_percentage,
        deal_value=c.deal_value,
        amount=c.amount,
        currency=c.currency,
        status=c.status.value,
        notes=c.notes,
        calculated_at=c.calculated_at,
        approved_at=c.approved_at,
        paid_at=c.paid_at,
        deal_customer_name=c.deal.customer_name if c.deal else None,
        deal_expected_close_date=str(c.deal.expected_close_date) if c.deal and c.deal.expected_close_date else None,
    )


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------

async def calculate_commission_for_deal(
    db: AsyncSession, deal_id: int
) -> Optional[Commission]:
    """
    Idempotent: creates a Commission row for an APPROVED deal if one doesn't
    already exist. Snapshots tier + rate at the time of calculation.
    """
    # Short-circuit if a commission already exists for this deal
    existing = await db.execute(
        select(Commission).where(Commission.deal_id == deal_id)
    )
    already = existing.scalar_one_or_none()
    if already is not None:
        return already

    deal_result = await db.execute(
        select(DealRegistration)
        .options(joinedload(DealRegistration.company))
        .where(DealRegistration.id == deal_id, DealRegistration.deleted_at.is_(None))
    )
    deal = deal_result.scalar_one_or_none()
    if deal is None:
        raise NotFoundException(code="DEAL_NOT_FOUND", message="Deal not found")

    if deal.status != DealStatus.APPROVED:
        # Silently skip — we only commission on approved deals
        logger.info("commission.skip_non_approved", deal_id=deal_id, status=deal.status.value)
        return None

    if not deal.company:
        logger.warning("commission.no_company", deal_id=deal_id)
        return None

    tier: PartnerTier = deal.company.tier
    rate = await _get_active_rate(db, tier, as_of=date.today())

    deal_value = Decimal(deal.estimated_value)
    amount = _quantize(deal_value * rate / Decimal("100"))

    commission = Commission(
        deal_id=deal.id,
        company_id=deal.company_id,
        user_id=deal.registered_by,
        tier_at_calculation=tier,
        rate_percentage=rate,
        deal_value=_quantize(deal_value),
        amount=amount,
        currency="USD",
        status=CommissionStatus.PENDING,
    )
    db.add(commission)
    await db.flush()

    await write_audit_log(
        db,
        deal.approved_by or 0,
        "CREATE",
        "commission",
        commission.id,
        {
            "deal_id": deal.id,
            "tier": tier.value,
            "rate": str(rate),
            "amount": str(amount),
        },
    )

    # Notify the partner who registered the deal
    try:
        await notify_user(
            db,
            deal.registered_by,
            "commission_created",
            "Commission Recorded",
            f"A commission of ${amount:,.2f} ({rate}%) has been recorded for deal: {deal.customer_name}",
            "commission",
            commission.id,
            send_email_flag=False,
        )
    except Exception as exc:  # pragma: no cover — notification is best-effort
        logger.warning("commission.notify_failed", error=str(exc), commission_id=commission.id)

    return commission


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

async def list_commissions(
    db: AsyncSession,
    *,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    scope_company_ids: Optional[list[int]] = None,
) -> tuple[list[CommissionRead], int]:
    query = (
        select(Commission)
        .options(
            joinedload(Commission.company),
            joinedload(Commission.user),
            joinedload(Commission.deal),
        )
    )
    count_query = select(func.count(Commission.id))

    # Partners are scoped to their company
    if current_user.role == UserRole.PARTNER:
        if not current_user.company_id:
            return [], 0
        query = query.where(Commission.company_id == current_user.company_id)
        count_query = count_query.where(Commission.company_id == current_user.company_id)
    else:
        # Channel-manager scope: only commissions for managed companies
        if scope_company_ids is not None:
            query = query.where(Commission.company_id.in_(scope_company_ids))
            count_query = count_query.where(Commission.company_id.in_(scope_company_ids))
        if company_id:
            query = query.where(Commission.company_id == company_id)
            count_query = count_query.where(Commission.company_id == company_id)

    if status:
        query = query.where(Commission.status == status)
        count_query = count_query.where(Commission.status == status)

    query = query.order_by(desc(Commission.calculated_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.unique().scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    items = [_build_commission_read(c) for c in rows]
    return items, total


async def get_commission(
    db: AsyncSession, *, commission_id: int, current_user: User
) -> CommissionRead:
    result = await db.execute(
        select(Commission)
        .options(
            joinedload(Commission.company),
            joinedload(Commission.user),
            joinedload(Commission.deal),
        )
        .where(Commission.id == commission_id)
    )
    c = result.unique().scalar_one_or_none()
    if c is None:
        raise NotFoundException(code="COMMISSION_NOT_FOUND", message="Commission not found")

    if current_user.role == UserRole.PARTNER and c.company_id != current_user.company_id:
        raise NotFoundException(code="COMMISSION_NOT_FOUND", message="Commission not found")

    return _build_commission_read(c)


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    CommissionStatus.PENDING: {CommissionStatus.APPROVED, CommissionStatus.VOID},
    CommissionStatus.APPROVED: {CommissionStatus.PAID, CommissionStatus.VOID},
    CommissionStatus.PAID: set(),
    CommissionStatus.VOID: set(),
}


async def update_commission_status(
    db: AsyncSession,
    *,
    commission_id: int,
    new_status: str,
    notes: Optional[str],
    actor: User,
) -> CommissionRead:
    try:
        target = CommissionStatus(new_status)
    except ValueError:
        raise BadRequestException(
            code="INVALID_STATUS", message=f"Unknown status: {new_status}"
        )

    result = await db.execute(
        select(Commission)
        .options(
            joinedload(Commission.company),
            joinedload(Commission.user),
            joinedload(Commission.deal),
        )
        .where(Commission.id == commission_id)
    )
    c = result.unique().scalar_one_or_none()
    if c is None:
        raise NotFoundException(code="COMMISSION_NOT_FOUND", message="Commission not found")

    allowed = VALID_TRANSITIONS[c.status]
    if target not in allowed:
        raise BadRequestException(
            code="INVALID_TRANSITION",
            message=f"Cannot transition commission from {c.status.value} to {target.value}",
        )

    before = c.status.value
    c.status = target
    now = datetime.now(timezone.utc)
    if target == CommissionStatus.APPROVED:
        c.approved_at = now
    elif target == CommissionStatus.PAID:
        if c.approved_at is None:
            c.approved_at = now
        c.paid_at = now
    if notes:
        c.notes = (c.notes + "\n---\n" if c.notes else "") + notes

    await db.flush()
    await write_audit_log(
        db,
        actor.id,
        "UPDATE",
        "commission",
        c.id,
        {"before": {"status": before}, "after": {"status": target.value}},
    )

    if c.user_id:
        try:
            await notify_user(
                db,
                c.user_id,
                f"commission_{target.value}",
                f"Commission {target.value.title()}",
                f"Commission of ${c.amount:,.2f} is now {target.value}.",
                "commission",
                c.id,
                send_email_flag=False,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("commission.status_notify_failed", error=str(exc))

    return _build_commission_read(c)


# ---------------------------------------------------------------------------
# Scorecard + leaderboard
# ---------------------------------------------------------------------------

def _next_tier(current: PartnerTier) -> Optional[PartnerTier]:
    try:
        idx = TIER_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(TIER_ORDER):
        return None
    return TIER_ORDER[idx + 1]


def _tier_progress_pct(current: PartnerTier, approved_deal_count: int) -> float:
    target = _next_tier(current)
    if target is None:
        return 100.0
    threshold = TIER_THRESHOLDS[target]
    if threshold <= 0:
        return 100.0
    pct = (approved_deal_count / threshold) * 100
    return float(min(100.0, max(0.0, pct)))


async def _monthly_commission_series(
    db: AsyncSession, company_id: int, months_back: int = 6
) -> list[MonthlyCommissionPoint]:
    result = await db.execute(
        select(
            func.to_char(Commission.calculated_at, "YYYY-MM").label("month"),
            func.sum(Commission.amount).label("total"),
        )
        .where(
            Commission.company_id == company_id,
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID, CommissionStatus.PENDING]),
        )
        .group_by("month")
        .order_by("month")
    )
    rows = result.all()
    return [
        MonthlyCommissionPoint(month=row.month, amount=Decimal(row.total or 0))
        for row in rows[-months_back:]
    ]


async def get_scorecard(
    db: AsyncSession, *, company_id: int, current_user: User
) -> ScorecardRead:
    if current_user.role == UserRole.PARTNER and current_user.company_id != company_id:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    company_result = await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = company_result.scalar_one_or_none()
    if company is None:
        raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")

    # Approved deal count
    approved_deals_result = await db.execute(
        select(func.count(DealRegistration.id)).where(
            DealRegistration.company_id == company_id,
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.deleted_at.is_(None),
        )
    )
    approved_deals = approved_deals_result.scalar() or 0

    # Total closed value (approved deals)
    total_value_result = await db.execute(
        select(func.coalesce(func.sum(DealRegistration.estimated_value), 0)).where(
            DealRegistration.company_id == company_id,
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.deleted_at.is_(None),
        )
    )
    total_closed_value = Decimal(total_value_result.scalar() or 0)

    # YTD commission (calendar year)
    year_start = date(date.today().year, 1, 1)
    ytd_result = await db.execute(
        select(func.coalesce(func.sum(Commission.amount), 0)).where(
            Commission.company_id == company_id,
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID, CommissionStatus.PENDING]),
            Commission.calculated_at >= year_start,
        )
    )
    ytd_commission = Decimal(ytd_result.scalar() or 0)

    lifetime_result = await db.execute(
        select(func.coalesce(func.sum(Commission.amount), 0)).where(
            Commission.company_id == company_id,
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID]),
        )
    )
    lifetime_commission = Decimal(lifetime_result.scalar() or 0)

    # Rank via subquery
    rank_result = await db.execute(
        select(Commission.company_id, func.sum(Commission.amount).label("total"))
        .where(
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID]),
            Commission.calculated_at >= year_start,
        )
        .group_by(Commission.company_id)
        .order_by(desc("total"))
    )
    leaderboard = rank_result.all()
    rank: Optional[int] = None
    for idx, row in enumerate(leaderboard, start=1):
        if row.company_id == company_id:
            rank = idx
            break

    badges: list[Badge] = []
    if approved_deals >= 1:
        badges.append(Badge(key="first_deal", label="First Deal", description="Closed your first deal"))
    if approved_deals >= 10:
        badges.append(Badge(key="ten_deals", label="10 Deals Closed", description="Closed 10+ deals"))
    if ytd_commission >= Decimal("100000"):
        badges.append(Badge(key="100k_ytd", label="$100k+ YTD", description="Earned $100k+ in commissions YTD"))
    if company.tier == PartnerTier.PLATINUM:
        badges.append(Badge(key="platinum", label="Platinum Tier", description="Reached Platinum tier"))

    monthly_series = await _monthly_commission_series(db, company_id)
    next_tier = _next_tier(company.tier)

    return ScorecardRead(
        company_id=company.id,
        company_name=company.name,
        tier=company.tier.value,
        next_tier=next_tier.value if next_tier else None,
        total_approved_deals=approved_deals,
        total_closed_value=_quantize(total_closed_value),
        ytd_commission=_quantize(ytd_commission),
        lifetime_commission=_quantize(lifetime_commission),
        tier_progress_pct=_tier_progress_pct(company.tier, approved_deals),
        rank=rank,
        badges=badges,
        monthly_commission=monthly_series,
    )


async def get_leaderboard(
    db: AsyncSession, *, limit: int = 10, period: str = "ytd"
) -> LeaderboardResponse:
    if period == "ytd":
        start_date = date(date.today().year, 1, 1)
    elif period == "30d":
        today = date.today()
        start_date = date(today.year, today.month, 1)
    else:  # "all"
        start_date = date(1970, 1, 1)

    result = await db.execute(
        select(
            Company.id,
            Company.name,
            Company.tier,
            func.coalesce(func.sum(Commission.amount), 0).label("total"),
            func.count(Commission.id).label("deal_count"),
        )
        .join(Commission, Commission.company_id == Company.id)
        .where(
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID]),
            Commission.calculated_at >= start_date,
            Company.deleted_at.is_(None),
        )
        .group_by(Company.id, Company.name, Company.tier)
        .order_by(desc("total"))
        .limit(limit)
    )
    rows = result.all()

    entries: list[LeaderboardEntry] = []
    for idx, row in enumerate(rows, start=1):
        entries.append(
            LeaderboardEntry(
                rank=idx,
                company_id=row.id,
                company_name=row.name,
                tier=row.tier.value if hasattr(row.tier, "value") else str(row.tier),
                total_amount=_quantize(Decimal(row.total)),
                deal_count=int(row.deal_count),
            )
        )
    return LeaderboardResponse(period=period, entries=entries)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

async def build_statement(
    db: AsyncSession, *, company_id: int, period_start: date, period_end: date
) -> tuple[list[Commission], Decimal]:
    result = await db.execute(
        select(Commission)
        .options(joinedload(Commission.deal), joinedload(Commission.company))
        .where(
            Commission.company_id == company_id,
            Commission.calculated_at >= period_start,
            Commission.calculated_at <= period_end,
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID]),
        )
        .order_by(Commission.calculated_at)
    )
    rows = list(result.unique().scalars().all())
    total = sum((c.amount for c in rows), Decimal("0"))
    return rows, _quantize(total)


async def list_statements(
    db: AsyncSession, *, company_id: Optional[int], current_user: User
) -> list[StatementPeriodSummary]:
    """
    Returns monthly summaries rolled up from Commission rows. We don't
    pre-materialize them — cheap to compute at request time.
    """
    query = (
        select(
            Commission.company_id,
            func.date_trunc("month", Commission.calculated_at).label("period"),
            func.coalesce(func.sum(Commission.amount), 0).label("total"),
            func.count(Commission.id).label("cnt"),
        )
        .where(
            Commission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID]),
        )
        .group_by(Commission.company_id, "period")
        .order_by(desc("period"))
    )

    if current_user.role == UserRole.PARTNER:
        if not current_user.company_id:
            return []
        query = query.where(Commission.company_id == current_user.company_id)
    elif company_id:
        query = query.where(Commission.company_id == company_id)

    result = await db.execute(query)
    rows = result.all()

    # Fetch company names in a single follow-up query
    company_ids = {r.company_id for r in rows}
    name_map: dict[int, str] = {}
    if company_ids:
        name_result = await db.execute(
            select(Company.id, Company.name).where(Company.id.in_(company_ids))
        )
        name_map = {row.id: row.name for row in name_result}

    summaries: list[StatementPeriodSummary] = []
    for row in rows:
        period_start_dt: datetime = row.period
        # Last day of the month
        if period_start_dt.month == 12:
            next_month = period_start_dt.replace(year=period_start_dt.year + 1, month=1)
        else:
            next_month = period_start_dt.replace(month=period_start_dt.month + 1)
        period_end = (next_month - timedelta(days=1)).date()
        summaries.append(
            StatementPeriodSummary(
                period_start=period_start_dt.date(),
                period_end=period_end,
                company_id=row.company_id,
                company_name=name_map.get(row.company_id),
                total_amount=_quantize(Decimal(row.total)),
                commission_count=int(row.cnt),
            )
        )
    return summaries
