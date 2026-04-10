from fastapi import APIRouter, Depends, Query, Response, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin, get_current_partner
from app.models.user import User, UserRole
from app.schemas.opportunity import (
    OpportunityCreateRequest,
    OpportunityUpdateRequest,
    OpportunityResponse,
    OpportunityApproveRequest,
    OpportunityRejectRequest,
    OpportunityInternalNoteRequest,
    OppDocumentResponse,
)
from app.schemas.common import MessageResponse
from app.services import opportunity_service
from app.utils.file_upload import save_upload
from app.core.exceptions import ForbiddenException

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.post("", response_model=OpportunityResponse, status_code=201)
async def create_opportunity(
    data: OpportunityCreateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.create_opportunity(db, data, partner)


@router.get("", status_code=200)
async def list_opportunities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    channel_manager_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    submitted_by = None
    if current_user.role == UserRole.PARTNER:
        submitted_by = current_user.id
        company_id = current_user.company_id

    items, total = await opportunity_service.get_opportunities(
        db, page, page_size, status, company_id, country, region, search,
        submitted_by, channel_manager_id,
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{opp_id}", response_model=OpportunityResponse, status_code=200)
async def get_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    opp = await opportunity_service.get_opportunity_detail(db, opp_id)

    if current_user.role == UserRole.PARTNER and opp.submitted_by != current_user.id:
        raise ForbiddenException(message="You can only view your own opportunities")

    if current_user.role == UserRole.ADMIN:
        opp = await opportunity_service.auto_mark_under_review(db, opp_id, current_user)
    elif current_user.role == UserRole.PARTNER:
        opp.internal_notes = None

    return opp


@router.put("/{opp_id}", response_model=OpportunityResponse, status_code=200)
async def update_opportunity(
    opp_id: int,
    data: OpportunityUpdateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.update_opportunity(db, opp_id, data, partner)


@router.post("/{opp_id}/submit", response_model=OpportunityResponse, status_code=200)
async def submit_opportunity(
    opp_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.submit_opportunity(db, opp_id, partner)


@router.post("/{opp_id}/approve", response_model=OpportunityResponse, status_code=200)
async def approve_opportunity(
    opp_id: int,
    data: OpportunityApproveRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.approve_opportunity(db, opp_id, data, admin)


@router.post("/{opp_id}/reject", response_model=OpportunityResponse, status_code=200)
async def reject_opportunity(
    opp_id: int,
    data: OpportunityRejectRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.reject_opportunity(db, opp_id, data, admin)


@router.post("/{opp_id}/review", response_model=OpportunityResponse, status_code=200)
async def mark_under_review(
    opp_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.mark_under_review(db, opp_id, admin)


@router.delete("/{opp_id}", response_model=MessageResponse, status_code=200)
async def remove_opportunity(
    opp_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await opportunity_service.remove_opportunity(db, opp_id, admin)
    return MessageResponse(message="Opportunity removed successfully")


@router.post("/{opp_id}/notes", response_model=OpportunityResponse, status_code=200)
async def add_internal_note(
    opp_id: int,
    data: OpportunityInternalNoteRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.add_internal_note(db, opp_id, data, admin)


@router.post("/{opp_id}/documents", response_model=OppDocumentResponse, status_code=201)
async def upload_opp_document(
    opp_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    file_info = await save_upload(file, subdirectory=f"opportunities/{opp_id}")
    return await opportunity_service.add_opp_document(db, opp_id, file_info)


@router.delete("/{opp_id}/documents/{doc_id}", status_code=204)
async def delete_opp_document(
    opp_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await opportunity_service.remove_opp_document(db, opp_id, doc_id, current_user)
    return Response(status_code=204)
