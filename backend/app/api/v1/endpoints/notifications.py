from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import math

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.notification import NotificationResponse, NotificationCountResponse, MarkReadRequest
from app.schemas.common import MessageResponse
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", status_code=200)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await notification_service.get_user_notifications(
        db, current_user.id, page, page_size, unread_only
    )
    return {
        "items": [
            NotificationResponse.model_validate(n).model_dump() for n in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/count", response_model=NotificationCountResponse, status_code=200)
async def get_notification_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    unread = await notification_service.get_unread_count(db, current_user.id)
    return NotificationCountResponse(unread_count=unread, total_count=0)


@router.post("/mark-read", response_model=MessageResponse, status_code=200)
async def mark_as_read(
    data: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await notification_service.mark_notifications_read(db, current_user.id, data.notification_ids)
    return MessageResponse(message=f"{count} notifications marked as read")


@router.post("/mark-all-read", response_model=MessageResponse, status_code=200)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await notification_service.mark_all_read(db, current_user.id)
    return MessageResponse(message=f"{count} notifications marked as read")
