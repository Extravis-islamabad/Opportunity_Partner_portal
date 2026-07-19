"""POC and post-PO customer licence endpoints.

Reads are open to admins, sales reps, and partners (each scoped to what they
own). Writes are admin + sales rep only — partners see POC progress on their
opportunities but don't drive it.

Every handler that touches a single record calls assert_can_access_opportunity
against the *parent opportunity*, because that's where ownership lives: a POC
has no company_id or sales_rep_id of its own.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import (
    assert_can_access_opportunity,
    get_admin_scope,
    get_current_user,
    get_poc_editor,
)
from app.models.user import User, UserRole
from app.schemas.poc import (
    LicenseResponse,
    LicenseUpsertRequest,
    PocCloseRequest,
    PocResponse,
    PocStageUpdateRequest,
    PocStartRequest,
    PocUpdateRequest,
)
from app.services import poc_service

router = APIRouter(prefix="/pocs", tags=["POC"])


async def _list_scope(db: AsyncSession, user: User) -> dict:
    """Translate the caller's role into list-query filters.

    Returns kwargs for poc_service.list_pocs / list_licenses. Partners are
    scoped by their company; sales reps by assignment; channel-manager admins
    by managed companies; superadmins unscoped.
    """
    if user.role == UserRole.PARTNER:
        # A partner with no company sees nothing (empty list, not everything).
        return {"scope_company_ids": [user.company_id] if user.company_id else []}
    if user.role == UserRole.SALES_REP:
        return {"sales_rep_id": user.id}
    return {"scope_company_ids": await get_admin_scope(db, user)}


# ---------------------------------------------------------------------------
# POC — list & read
# ---------------------------------------------------------------------------

@router.get("", status_code=200)
async def list_pocs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(not_started|running|successful|unsuccessful)$"),
    country: Optional[str] = None,
    company_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await poc_service.list_pocs(
        db,
        page=page,
        page_size=page_size,
        status=status,
        country=country,
        company_id=company_id,
        search=search,
        **await _list_scope(db, current_user),
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/by-opportunity/{opp_id}", response_model=Optional[PocResponse], status_code=200)
async def get_poc_for_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The POC for an opportunity, or null if one hasn't started yet. Null is
    a normal state (most opportunities never reach POC), so this returns 200
    with a null body rather than 404."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_access_opportunity(db, current_user, opp)

    poc = await poc_service.get_poc_by_opportunity(db, opp_id)
    return poc_service.to_poc_response(poc) if poc else None


@router.get("/{poc_id}", response_model=PocResponse, status_code=200)
async def get_poc(
    poc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, current_user, poc.opportunity)
    return poc_service.to_poc_response(poc)


# ---------------------------------------------------------------------------
# POC — writes
# ---------------------------------------------------------------------------

@router.post("/by-opportunity/{opp_id}/start", response_model=PocResponse, status_code=201)
async def start_poc(
    opp_id: int,
    data: PocStartRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Start the POC by recording the VM allocation."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_access_opportunity(db, user, opp)
    return await poc_service.start_poc(db, opp_id, data, user)


@router.put("/{poc_id}", response_model=PocResponse, status_code=200)
async def update_poc(
    poc_id: int,
    data: PocUpdateRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, user, poc.opportunity)
    return await poc_service.update_poc(db, poc_id, data, user)


@router.put("/{poc_id}/stages/{stage_key}", response_model=PocResponse, status_code=200)
async def set_poc_stage(
    poc_id: int,
    stage_key: str,
    data: PocStageUpdateRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Tick a stage complete, or clear it by sending completed_at: null."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, user, poc.opportunity)
    return await poc_service.set_stage(db, poc_id, stage_key, data.completed_at, user)


@router.post("/{poc_id}/close", response_model=PocResponse, status_code=200)
async def close_poc(
    poc_id: int,
    data: PocCloseRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, user, poc.opportunity)
    return await poc_service.close_poc(db, poc_id, data, user)


@router.post("/{poc_id}/reopen", response_model=PocResponse, status_code=200)
async def reopen_poc(
    poc_id: int,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, user, poc.opportunity)
    return await poc_service.reopen_poc(db, poc_id, user)


# ---------------------------------------------------------------------------
# Customer licences (post-PO)
# ---------------------------------------------------------------------------

@router.get("/licenses/list", status_code=200)
async def list_licenses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(pending_activation|active|expiring_soon|expired)$"),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await poc_service.list_licenses(
        db,
        page=page,
        page_size=page_size,
        status=status,
        search=search,
        **await _list_scope(db, current_user),
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/licenses/by-opportunity/{opp_id}", response_model=Optional[LicenseResponse], status_code=200)
async def get_license_for_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Null when no PO has landed yet — the normal case for pipeline opps."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_access_opportunity(db, current_user, opp)

    lic = await poc_service.get_license_by_opportunity(db, opp_id)
    return poc_service.to_license_response(lic) if lic else None


@router.put("/licenses/by-opportunity/{opp_id}", response_model=LicenseResponse, status_code=200)
async def upsert_license(
    opp_id: int,
    data: LicenseUpsertRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_access_opportunity(db, user, opp)
    return await poc_service.upsert_license(db, opp_id, data, user)
