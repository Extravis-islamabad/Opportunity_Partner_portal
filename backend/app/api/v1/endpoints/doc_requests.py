from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin, get_current_partner
from app.models.user import User, UserRole
from app.schemas.doc_request import (
    DocRequestCreateRequest,
    DocRequestFulfillRequest,
    DocRequestDeclineRequest,
    DocRequestResponse,
)
from app.schemas.common import MessageResponse
from app.services import doc_request_service
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/doc-requests", tags=["Document Requests"])


@router.post("", response_model=DocRequestResponse, status_code=201)
async def create_doc_request(
    data: DocRequestCreateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await doc_request_service.create_doc_request(db, data, partner)


@router.get("", status_code=200)
async def list_doc_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    requested_by = None
    if current_user.role == UserRole.PARTNER:
        requested_by = current_user.id

    items, total = await doc_request_service.get_doc_requests(
        db, page, page_size, status, company_id, requested_by
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{request_id}", response_model=DocRequestResponse, status_code=200)
async def get_doc_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await doc_request_service.get_doc_request_detail(db, request_id)


@router.post("/{request_id}/fulfill", response_model=DocRequestResponse, status_code=200)
async def fulfill_doc_request(
    request_id: int,
    add_to_kb: bool = Query(False),
    kb_title: Optional[str] = Query(None),
    kb_category: Optional[str] = Query(None),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    file_info = await save_upload(file, subdirectory="doc-requests")
    data = DocRequestFulfillRequest(
        add_to_kb=add_to_kb,
        kb_title=kb_title,
        kb_category=kb_category,
    )
    return await doc_request_service.fulfill_doc_request(db, request_id, file_info, data, admin)


@router.post("/{request_id}/decline", response_model=DocRequestResponse, status_code=200)
async def decline_doc_request(
    request_id: int,
    data: DocRequestDeclineRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await doc_request_service.decline_doc_request(db, request_id, data, admin)
