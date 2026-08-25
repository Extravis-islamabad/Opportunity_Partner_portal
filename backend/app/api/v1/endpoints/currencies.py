"""Currencies and the rates deals are converted at."""
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_superadmin, get_current_user
from app.models.currency import REPORTING_CURRENCY, Currency
from app.models.user import User
from app.services import currency_service

router = APIRouter(prefix="/currencies", tags=["Currencies"])


class RateUpdateRequest(BaseModel):
    """A new rate for one currency, in units of the reporting currency."""

    rate_to_usd: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6)


@router.get("", status_code=200)
async def list_currencies(
    # Any signed-in user: the currency picker on the opportunity form needs
    # this, and a list of exchange rates is not sensitive.
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every currency with its current rate."""
    return {
        "reporting_currency": REPORTING_CURRENCY.value,
        "currencies": await currency_service.list_rates(db),
    }


@router.put("/{currency}", status_code=200)
async def set_rate(
    currency: str,
    data: RateUpdateRequest,
    # Superadmin only: a rate decides what every future deal in that currency
    # is reported and paid commission on.
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Publish a new rate, closing the one it replaces.

    Deals already recorded keep the rate they were converted at — the point of
    stamping it on the row — so this changes what future deals are worth, not
    what past ones were.
    """
    row = await currency_service.set_rate(db, currency, data.rate_to_usd, admin)
    return {
        "currency": row.currency.value,
        # Stringified for the same reason as the list: a rate is a small number
        # where float rounding is visible and wrong.
        "rate_to_usd": str(row.rate_to_usd),
        "effective_from": row.effective_from,
    }
