from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin
from app.core.exceptions import UnprocessableException
from app.models.user import User, UserRole
from app.schemas.knowledge_base import (
    KBDocumentCreateRequest,
    KBDocumentUpdateRequest,
    KBDocumentResponse,
    KBCategoryResponse,
)
from app.schemas.common import MessageResponse
from app.services import kb_service
from app.utils.file_upload import save_upload, delete_upload

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


def _validated(model: type[BaseModel], **fields) -> BaseModel:
    """Build a request model from form fields, turning a pydantic failure into
    the same clean 422 the JSON routes give. Constructed by hand, a
    ValidationError otherwise fell through to the generic ValueError handler
    and came back as a 400 carrying pydantic's raw dump."""
    try:
        return model(**fields)
    except ValidationError as exc:
        errors = [
            {"field": " -> ".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        first = errors[0]
        raise UnprocessableException(
            code="VALIDATION_ERROR",
            message=f"{first['field']}: {first['message']}" if first["field"] else first["message"],
            details={"errors": errors},
        )


@router.post("/documents", response_model=KBDocumentResponse, status_code=201)
async def upload_kb_document(
    title: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Validate everything we can BEFORE the bytes are written, so a rejected
    # request doesn't leave an orphan file on disk.
    data = _validated(
        KBDocumentCreateRequest, title=title, category=category,
        description=description or None,
    )
    data.category = await kb_service.validate_category(db, data.category)
    file_info = await save_upload(file, subdirectory="knowledge-base")
    try:
        return await kb_service.create_kb_document(db, data, file_info, admin)
    except Exception:
        delete_upload(file_info["file_url"])
        raise


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
        "items": [item.model_dump(mode="json") for item in items],
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
    # Admins may open a superseded version (via previous_version_id);
    # everyone else only ever sees the current one.
    return await kb_service.get_kb_document_detail(
        db, doc_id, include_archived=current_user.role == UserRole.ADMIN,
    )


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
    # Multipart can't say "absent" vs "null", so: a field not sent is None and
    # is left untouched; title/category sent empty are rejected (both NOT
    # NULL); description sent empty clears it — the edit form's way to blank it.
    fields: dict = {}
    if title is not None:
        fields["title"] = title
    if category is not None:
        fields["category"] = category
    if description is not None:
        fields["description"] = description.strip() or None
    data = _validated(KBDocumentUpdateRequest, **fields)
    if data.category is not None:
        data.category = await kb_service.validate_category(db, data.category)

    new_file_info = None
    if file:
        new_file_info = await save_upload(file, subdirectory="knowledge-base")
    try:
        return await kb_service.update_kb_document(db, doc_id, data, admin, new_file_info)
    except Exception:
        if new_file_info:
            delete_upload(new_file_info["file_url"])
        raise


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
    return await kb_service.get_download_link(
        db, doc_id, current_user.id,
        include_archived=current_user.role == UserRole.ADMIN,
    )
