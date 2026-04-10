"""
Commission & scorecard endpoints.

Partners see their own company only. Admins see everything. Admins/channel
managers can transition commission status.
"""
import math
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user
from app.models.user import User, UserRole
from app.schemas.commission import (
    CommissionListResponse,
    CommissionRead,
    CommissionStatusUpdate,
    LeaderboardResponse,
    ScorecardRead,
    StatementPeriodSummary,
)
from app.services import commission_service
from app.services.export_service import _make_pdf_doc, _pdf_header_elements, _pdf_table
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

router = APIRouter(tags=["Commissions"])


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------

@router.get("/commissions", response_model=CommissionListResponse)
async def list_commissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommissionListResponse:
    items, total = await commission_service.list_commissions(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        status=status,
        company_id=company_id,
    )
    return CommissionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/commissions/{commission_id}", response_model=CommissionRead)
async def get_commission(
    commission_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommissionRead:
    return await commission_service.get_commission(
        db, commission_id=commission_id, current_user=current_user
    )


@router.patch("/commissions/{commission_id}/status", response_model=CommissionRead)
async def update_commission_status(
    commission_id: int,
    payload: CommissionStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CommissionRead:
    return await commission_service.update_commission_status(
        db,
        commission_id=commission_id,
        new_status=payload.status,
        notes=payload.notes,
        actor=admin,
    )


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@router.get("/commissions/statements/list", response_model=list[StatementPeriodSummary])
async def list_statements(
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StatementPeriodSummary]:
    return await commission_service.list_statements(
        db, company_id=company_id, current_user=current_user
    )


@router.get("/commissions/statements/{company_id}/{period}.pdf")
async def download_statement_pdf(
    company_id: int,
    period: str,  # "YYYY-MM"
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    if current_user.role == UserRole.PARTNER and current_user.company_id != company_id:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException(message="You can only access your own statements")

    try:
        year, month = map(int, period.split("-"))
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year + 1, 1, 1)
        else:
            period_end = date(year, month + 1, 1)
    except (ValueError, IndexError):
        from app.core.exceptions import BadRequestException

        raise BadRequestException(code="INVALID_PERIOD", message="Period must be YYYY-MM")

    rows, total = await commission_service.build_statement(
        db, company_id=company_id, period_start=period_start, period_end=period_end
    )

    # Build PDF inline — reuses the shared export helpers
    from io import BytesIO

    buf = BytesIO()
    doc = _make_pdf_doc(buf, f"Commission Statement — {period}")
    company_name = rows[0].company.name if rows and rows[0].company else f"Company #{company_id}"
    elements = _pdf_header_elements(
        f"Commission Statement — {period}",
        subtitle=f"{company_name} · Total ${total:,.2f}",
    )

    headers = ["Deal", "Calculated", "Tier", "Rate", "Deal Value", "Commission", "Status"]
    table_rows = []
    for c in rows:
        table_rows.append(
            [
                c.deal.customer_name if c.deal else f"#{c.deal_id}",
                c.calculated_at.strftime("%Y-%m-%d"),
                c.tier_at_calculation.value.title(),
                f"{c.rate_percentage}%",
                f"${c.deal_value:,.2f}",
                f"${c.amount:,.2f}",
                c.status.value.title(),
            ]
        )

    if table_rows:
        col_widths = [60 * mm, 26 * mm, 22 * mm, 18 * mm, 30 * mm, 30 * mm, 24 * mm]
        elements.append(_pdf_table(headers, table_rows, col_widths))
    else:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No commissions in this period.", styles["Italic"]))

    doc.build(elements)
    buf.seek(0)

    filename = f"commission-statement-{company_id}-{period}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Scorecard + leaderboard
# ---------------------------------------------------------------------------

@router.get("/scorecard/me", response_model=ScorecardRead)
async def get_my_scorecard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScorecardRead:
    if not current_user.company_id:
        from app.core.exceptions import BadRequestException

        raise BadRequestException(
            code="NO_COMPANY", message="User is not associated with a company"
        )
    return await commission_service.get_scorecard(
        db, company_id=current_user.company_id, current_user=current_user
    )


@router.get("/scorecard/{company_id}", response_model=ScorecardRead)
async def get_company_scorecard(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScorecardRead:
    return await commission_service.get_scorecard(
        db, company_id=company_id, current_user=current_user
    )


@router.get("/scorecard/leaderboard/top", response_model=LeaderboardResponse)
async def get_leaderboard(
    limit: int = Query(10, ge=1, le=50),
    period: str = Query("ytd", pattern="^(ytd|30d|all)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    return await commission_service.get_leaderboard(db, limit=limit, period=period)
