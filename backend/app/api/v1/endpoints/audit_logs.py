import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_superadmin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=AuditLogListResponse, status_code=200)
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(AuditLog, User.full_name.label("user_full_name"))
        .join(User, AuditLog.user_id == User.id)
    )
    count_query = select(func.count(AuditLog.id))

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
        count_query = count_query.where(AuditLog.entity_id == entity_id)
    if date_from is not None:
        query = query.where(AuditLog.timestamp >= date_from)
        count_query = count_query.where(AuditLog.timestamp >= date_from)
    if date_to is not None:
        query = query.where(AuditLog.timestamp <= date_to)
        count_query = count_query.where(AuditLog.timestamp <= date_to)

    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = [
        AuditLogResponse(
            id=row.AuditLog.id,
            user_id=row.AuditLog.user_id,
            user_full_name=row.user_full_name,
            action=row.AuditLog.action,
            entity_type=row.AuditLog.entity_type,
            entity_id=row.AuditLog.entity_id,
            metadata_json=row.AuditLog.metadata_json,
            timestamp=row.AuditLog.timestamp,
        )
        for row in rows
    ]

    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )
