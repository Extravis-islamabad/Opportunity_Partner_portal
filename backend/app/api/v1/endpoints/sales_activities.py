"""Sales rep daily activity log.

Write access: sales reps on their own entries; superadmins may edit or
delete anyone's entry (the service enforces both). Read access: a rep reads
their own month; any admin may read any *rep's* month via ?user_id= (the
service refuses non-rep targets). Partners have no access to this module.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_sales_rep, get_current_user
from app.core.exceptions import ForbiddenException
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse
from app.schemas.sales_activity import (
    ActivityCreateRequest,
    ActivityMonthResponse,
    ActivityResponse,
    ActivityUpdateRequest,
)
from app.services import sales_activity_service

router = APIRouter(prefix="/activities", tags=["Sales Activities"])


@router.get("/month", response_model=ActivityMonthResponse, status_code=200)
async def get_activity_month(
    month: str = Query(..., description="Month in YYYY-MM format"),
    user_id: Optional[int] = Query(None, description="Rep to view (admins only)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == UserRole.ADMIN:
        # Admins default to their own (usually empty) log unless they pick a rep.
        target_id = user_id or current_user.id
    elif current_user.role == UserRole.SALES_REP:
        # A rep sees exactly their own log; a foreign user_id is refused
        # loudly rather than silently swapped, so a broken client is visible.
        if user_id is not None and user_id != current_user.id:
            raise ForbiddenException(message="You can only view your own activities")
        target_id = current_user.id
    else:
        raise ForbiddenException(message="Partners do not have access to activity logs")

    return await sales_activity_service.get_activity_month(
        db, target_id, month, viewer=current_user
    )


@router.post("", response_model=ActivityResponse, status_code=201)
async def create_activity(
    data: ActivityCreateRequest,
    rep: User = Depends(get_current_sales_rep),
    db: AsyncSession = Depends(get_db),
):
    return await sales_activity_service.create_activity(db, data, rep)


def _deny_partners(user: User) -> None:
    if user.role not in (UserRole.SALES_REP, UserRole.ADMIN):
        raise ForbiddenException(message="Partners do not have access to activity logs")


@router.put("/{activity_id}", response_model=ActivityResponse, status_code=200)
async def update_activity(
    activity_id: int,
    data: ActivityUpdateRequest,
    # get_current_user (not sales_rep): superadmins may also correct an
    # entry; the service restricts everyone else to their own.
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _deny_partners(current_user)
    return await sales_activity_service.update_activity(db, activity_id, data, current_user)


@router.delete("/{activity_id}", response_model=MessageResponse, status_code=200)
async def delete_activity(
    activity_id: int,
    # get_current_user (not sales_rep): superadmins may also delete an entry;
    # the service restricts everyone else to their own.
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _deny_partners(current_user)
    await sales_activity_service.delete_activity(db, activity_id, current_user)
    return MessageResponse(message="Activity deleted")
