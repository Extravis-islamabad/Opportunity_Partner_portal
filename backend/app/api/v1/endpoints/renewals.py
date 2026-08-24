"""Licences approaching expiry, and the renewals raised from them."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import (
    deny_customer_company,
    deny_sales_rep,
    get_admin_scope,
    get_current_user,
)
from app.models.user import User, UserRole
from app.services import renewal_service

router = APIRouter(prefix="/renewals", tags=["Renewals"])


class RenewalCreateRequest(BaseModel):
    """The two things a renewal genuinely re-decides. Everything else carries
    forward from the deployment being renewed."""

    worth: Optional[float] = Field(None, gt=0)
    closing_date: Optional[date] = None


@router.get("", status_code=200)
async def list_upcoming_renewals(
    days: Optional[int] = Query(None, ge=1, le=730),
    # A sales rep sees renewals for their own accounts through the opportunity
    # itself; this queue is the partner's and the channel manager's view of
    # their book, and a rep landing in the unscoped branch would read the lot.
    current_user: User = Depends(deny_sales_rep),
    _no_customer: User = Depends(deny_customer_company),
    db: AsyncSession = Depends(get_db),
):
    """Licences inside the renewal window, soonest first."""
    scope = None
    company_id = None
    if current_user.role == UserRole.PARTNER:
        company_id = current_user.company_id
        scope = [current_user.company_id] if current_user.company_id else []
    elif current_user.role == UserRole.ADMIN and not current_user.is_superadmin:
        scope = await get_admin_scope(db, current_user)

    return await renewal_service.upcoming_renewals(
        db, scope_company_ids=scope, company_id=company_id, days=days
    )


@router.post("/{license_id}", status_code=201)
async def create_renewal(
    license_id: int,
    data: RenewalCreateRequest,
    # Scoped per record inside the service: the incumbent partner, or an admin
    # who manages them.
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Raise the renewal for an expiring licence.

    Creates a draft opportunity carrying the deployment's details forward, and
    the deal registration alongside it that earns the commission.
    """
    renewal = await renewal_service.create_renewal(
        db, license_id, current_user, worth=data.worth, closing_date=data.closing_date
    )
    return {
        "id": renewal.id,
        "name": renewal.name,
        "status": renewal.status.value,
        "renewal_of_license_id": renewal.renewal_of_license_id,
    }
