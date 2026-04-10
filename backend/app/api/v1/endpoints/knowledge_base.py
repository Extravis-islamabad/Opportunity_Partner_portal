from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin
from app.models.user import User
from app.schemas.knowledge_base import (
    KBDocumentCreateRequest,
    KBDocumentUpdateRequest,
    KBDocumentResponse,
    KBCategoryResponse,
)
from app.schemas.common import MessageResponse
from app.services import kb_service
from app.utils.file_upload import save_upload

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


@router.post("/documents", response_model=KBDocumentResponse, status_code=201)
async def upload_kb_document(
    title: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    file_info = await save_upload(file, subdirectory="knowledge-base")
    data = KBDocumentCreateRequest(title=title, category=category, description=description)
    return await kb_service.create_kb_document(db, data, file_info, admin)


@router.get("/documents", status_code=200)
async def list_kb_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await kb_service.get_kb_documents(db, page, page_size, category, search)
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/categories", response_model=list[KBCategoryResponse], status_code=200)
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await kb_service.get_categories(db)


@router.get("/documents/{doc_id}", response_model=KBDocumentResponse, status_code=200)
async def get_kb_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await kb_service.get_kb_document_detail(db, doc_id)


@router.put("/documents/{doc_id}", response_model=KBDocumentResponse, status_code=200)
async def update_kb_document(
    doc_id: int,
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = KBDocumentUpdateRequest(title=title, category=category, description=description)
    new_file_info = None
    if file:
        new_file_info = await save_upload(file, subdirectory="knowledge-base")
    return await kb_service.update_kb_document(db, doc_id, data, admin, new_file_info)


@router.delete("/documents/{doc_id}", response_model=MessageResponse, status_code=200)
async def delete_kb_document(
    doc_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await kb_service.delete_kb_document(db, doc_id, admin)
    return MessageResponse(message="Document deleted successfully")


@router.post("/documents/{doc_id}/download", status_code=200)
async def download_kb_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await kb_service.get_kb_document_detail(db, doc_id)
    await kb_service.log_download(db, doc_id, current_user.id)
    return {"file_url": doc.file_url, "file_name": doc.file_name}
