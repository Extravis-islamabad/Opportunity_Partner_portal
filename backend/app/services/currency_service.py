"""The rate a deal was converted at, and where it comes from.

Conversion happens once, when a value is written, and the rate is stamped on
the row. Nothing here converts at read time — that is the whole design. A
report of last quarter's closed business must show the same numbers next year,
and it cannot if every read re-converts at today's rate.

That means a rate change applies to deals recorded after it, and leaves earlier
ones alone. Which is what a rate change means: the old deals really were worth
what they were worth.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.currency import (
    DEFAULT_RATES,
    REPORTING_CURRENCY,
    Currency,
    CurrencyRate,
)
from app.models.user import User
from app.utils.audit import write_audit_log


def normalise(value: str | Currency | None) -> Currency:
    """A currency code from whatever the caller had, defaulting to the
    reporting currency.

    None means "not stated", and everything in this system before multi-
    currency existed was implicitly USD — so that is what unstated means.
    """
    if value is None:
        return REPORTING_CURRENCY
    if isinstance(value, Currency):
        return value
    try:
        return Currency(value.strip().upper())
    except ValueError:
        raise BadRequestException(
            code="UNKNOWN_CURRENCY",
            message=f"{value} is not a currency we trade in",
        )


async def current_rate(db: AsyncSession, currency: str | Currency | None) -> Decimal:
    """What one unit of this currency is worth in the reporting currency now.

    Falls back to the built-in default when the table has no open row, rather
    than returning zero: a missing rate is a configuration problem, and valuing
    every deal in that currency at nothing would be a silent, expensive lie.
    """
    code = normalise(currency)
    if code == REPORTING_CURRENCY:
        return Decimal("1")

    row = (await db.execute(
        select(CurrencyRate).where(
            CurrencyRate.currency == code,
            CurrencyRate.effective_to.is_(None),
        )
    )).scalar_one_or_none()
    if row is not None:
        return Decimal(row.rate_to_usd)
    return Decimal(DEFAULT_RATES[code])


async def list_rates(db: AsyncSession) -> list[dict]:
    """Every currency with its current rate, in catalogue order.

    Includes the reporting currency at 1 so the UI can render one list rather
    than special-casing it.
    """
    rows = {
        r.currency: r
        for r in (await db.execute(
            select(CurrencyRate).where(CurrencyRate.effective_to.is_(None))
        )).scalars().all()
    }
    out = []
    for code in Currency:
        row = rows.get(code)
        rate = (
            Decimal("1") if code == REPORTING_CURRENCY
            else (Decimal(row.rate_to_usd) if row else Decimal(DEFAULT_RATES[code]))
        )
        out.append({
            "currency": code.value,
            # A string, not a Decimal: JSON has only floats, and a rate that
            # round-trips as 0.0033999999999999998 is not the rate anybody set.
            "rate_to_usd": str(rate),
            "effective_from": row.effective_from if row else None,
            # True when the number shown is the built-in fallback rather than
            # something somebody set, which is worth saying out loud on a page
            # that decides what deals are worth.
            "is_default": row is None and code != REPORTING_CURRENCY,
            "is_reporting_currency": code == REPORTING_CURRENCY,
        })
    return out


async def set_rate(
    db: AsyncSession, currency: str, rate: Decimal, actor: User
) -> CurrencyRate:
    """Publish a new rate, closing the one it replaces.

    The old row is dated rather than overwritten: deals already converted keep
    the rate they used, and this is the record that explains why one deal
    converted at 0.0036 and a later one at 0.0034.
    """
    code = normalise(currency)
    if code == REPORTING_CURRENCY:
        raise BadRequestException(
            code="REPORTING_CURRENCY_FIXED",
            message=f"{code.value} is the reporting currency — its rate is always 1",
        )
    if rate <= 0:
        raise BadRequestException(
            code="INVALID_RATE", message="A rate has to be greater than zero"
        )

    today = date.today()
    existing = (await db.execute(
        select(CurrencyRate).where(
            CurrencyRate.currency == code,
            CurrencyRate.effective_to.is_(None),
        )
    )).scalar_one_or_none()

    if existing is not None:
        if Decimal(existing.rate_to_usd) == rate:
            return existing
        existing.effective_to = today
        await db.flush()

    row = CurrencyRate(currency=code, rate_to_usd=rate, effective_from=today)
    db.add(row)
    await db.flush()

    await write_audit_log(
        db, actor.id, "UPDATE", "currency_rate", row.id,
        {
            "currency": code.value,
            "rate_to_usd": rate,
            "previous": existing.rate_to_usd if existing else None,
        },
    )
    return row


def reporting_value(amount, rate) -> Decimal | None:
    """amount × rate, in Python.

    The database has generated columns (`worth_usd`, `estimated_value_usd`)
    holding the same product, and those are what every aggregate sums. This is
    the same rule for a single record on the way out — the generated column is
    not populated on the row the INSERT returns, and reading it there costs a
    round trip that raises inside an async session.

    Two expressions of one rule, once for SQL and once for Python, in lockstep
    — the same shape as license_status_expr and derive_license_status. They
    take their inputs from the same two columns, so they cannot disagree.
    """
    if amount is None:
        return None
    return Decimal(amount) * Decimal(rate if rate is not None else 1)


async def stamp(db: AsyncSession, record, currency: str | Currency | None) -> None:
    """Set a record's currency and the rate to convert it, on the record.

    Called whenever the money on a row is created or changed. Both fields move
    together on purpose: a row whose currency was updated without its rate
    would report a riyal value converted at the dollar rate.
    """
    code = normalise(currency)
    record.currency = code
    record.exchange_rate_to_usd = await current_rate(db, code)
