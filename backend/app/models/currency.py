"""Money in more than one currency, reported in one.

Deals are done in USD, Saudi riyal, UAE dirham and Pakistani rupee, and every
value in this system was a bare number with no currency attached — so a 500,000
PKR deal and a 500,000 USD deal added up to a million of nothing.

Two pieces make that work:

  - the currency a deal was actually done in, stored on the deal;
  - the rate used to convert it, stored *on the same row* at the time the
    value was set.

Storing the rate rather than looking it up at read time is the whole point.
A report run today and the same report run next quarter must show the same
number for the same closed deal; if conversion happened at read time, every
historic figure would move whenever the rate moved. The rate on the row is a
record of what the deal was worth when it was done.
"""
import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
)

from app.core.database import Base


class Currency(str, enum.Enum):
    USD = "USD"
    SAR = "SAR"
    AED = "AED"
    PKR = "PKR"


# What everything is reported in. A constant rather than a setting: it is
# baked into the "Worth (USD)" column headers, the generated columns in the
# database and every chart axis, so changing it is a migration, not a config
# edit — and pretending otherwise would produce reports labelled in one
# currency holding numbers in another.
REPORTING_CURRENCY = Currency.USD

# Fallbacks used when the rates table has no row for a currency — the two
# pegged currencies at their peg, PKR at a round recent figure. Seeded into
# the table by the migration; kept here so a fresh install and a
# misconfigured one behave the same rather than silently valuing a deal at
# zero.
DEFAULT_RATES: dict[Currency, str] = {
    Currency.USD: "1.0",
    Currency.SAR: "0.2666",   # pegged at 3.75 SAR = 1 USD
    Currency.AED: "0.2723",   # pegged at 3.6725 AED = 1 USD
    Currency.PKR: "0.0036",
}


class CurrencyRate(Base):
    """What one unit of a currency was worth in the reporting currency, and
    when that was true.

    Dated rather than a single mutable number so a correction to today's rate
    does not silently restate what was recorded last year — and so the rate
    that was used on a deal can still be explained after it changes.
    """

    __tablename__ = "currency_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    currency = Column(
        Enum(Currency, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    # Multiply by this to get the reporting currency. Six decimal places
    # because PKR needs four to be useful at all and headroom is free.
    rate_to_usd = Column(Numeric(18, 6), nullable=False)

    effective_from = Column(Date, nullable=False, default=date.today)
    # Null means "still current". Closing a rate is what makes the history
    # readable rather than a pile of overlapping rows.
    effective_to = Column(Date, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_currency_rates_currency_from", "currency", "effective_from"),
        # One open rate per currency: two would make "the current rate"
        # ambiguous, and whichever the query happened to pick would decide
        # what a deal is worth.
        Index(
            "uq_currency_rates_current",
            "currency",
            unique=True,
            postgresql_where=effective_to.is_(None),
        ),
    )
