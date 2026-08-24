"""Read-only view of what the system tried to email.

Superadmin-only. The log carries recipient addresses and SMTP error text for
the whole deployment, which is not a channel manager's business — and the
question it answers ("is mail working at all") is a system question.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_superadmin
from app.models.email_delivery import EmailDelivery, EmailStatus
from app.models.user import User

router = APIRouter(prefix="/email-log", tags=["Email"])


@router.get("", status_code=200)
async def list_email_deliveries(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, pattern="^(sent|failed|skipped)$"),
    _admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    query = select(EmailDelivery)
    count_query = select(func.count(EmailDelivery.id))
    if status:
        query = query.where(EmailDelivery.status == status)
        count_query = count_query.where(EmailDelivery.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    rows = (await db.execute(
        query.order_by(EmailDelivery.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    # Counts by status alongside the page, so the answer to "is mail working"
    # does not depend on paging through to find a failure.
    tallies = dict(
        (await db.execute(
            select(EmailDelivery.status, func.count(EmailDelivery.id))
            .group_by(EmailDelivery.status)
        )).all()
    )

    return {
        "items": [
            {
                "id": r.id,
                "recipients": r.recipients,
                "subject": r.subject,
                "template": r.template,
                "status": r.status.value,
                "error": r.error,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
        "totals_by_status": {
            s.value: tallies.get(s, 0) for s in EmailStatus
        },
        # Surfaced so the page can say *why* everything is being skipped,
        # rather than showing rows and leaving the reason to be guessed.
        "email_configured": settings.email_is_configured,
    }
