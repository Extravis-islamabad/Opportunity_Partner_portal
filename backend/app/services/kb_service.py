from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.kb_document import KBDocument, KBDownloadLog
from app.models.user import User
from app.schemas.knowledge_base import (
    KBDocumentCreateRequest,
    KBDocumentUpdateRequest,
    KBDocumentResponse,
    KBCategoryResponse,
)
from app.core.exceptions import NotFoundException
from app.utils.audit import write_audit_log


async def create_kb_document(
    db: AsyncSession, data: KBDocumentCreateRequest, file_info: dict, admin_user: User
) -> KBDocumentResponse:
    doc = KBDocument(
        title=data.title,
        category=data.category,
        description=data.description,
        file_name=file_info["file_name"],
        file_url=file_info["file_url"],
        file_size=file_info.get("file_size"),
        content_type=file_info.get("content_type"),
        uploaded_by=admin_user.id,
    )
    db.add(doc)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "kb_document", doc.id, {"title": data.title})

    return KBDocumentResponse(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        description=doc.description,
        file_name=doc.file_name,
        file_url=doc.file_url,
        file_size=doc.file_size,
        content_type=doc.content_type,
        version=doc.version,
        uploaded_by=doc.uploaded_by,
        uploader_name=admin_user.full_name,
        download_count=0,
        published_at=doc.published_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def get_kb_documents(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list, int]:
    query = (
        select(KBDocument)
        .where(KBDocument.deleted_at.is_(None), KBDocument.is_archived == 0)
    )
    count_query = select(func.count(KBDocument.id)).where(
        KBDocument.deleted_at.is_(None), KBDocument.is_archived == 0
    )

    if category:
        query = query.where(KBDocument.category == category)
        count_query = count_query.where(KBDocument.category == category)

    if search:
        sf = KBDocument.title.ilike(f"%{search}%") | KBDocument.description.ilike(f"%{search}%")
        query = query.where(sf)
        count_query = count_query.where(sf)

    query = query.order_by(KBDocument.published_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    docs = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for d in docs:
        dl_count_result = await db.execute(
            select(func.count(KBDownloadLog.id)).where(KBDownloadLog.document_id == d.id)
        )
        dl_count = dl_count_result.scalar() or 0
        items.append(KBDocumentResponse(
            id=d.id,
            title=d.title,
            category=d.category,
            description=d.description,
            file_name=d.file_name,
            file_url=d.file_url,
            file_size=d.file_size,
            content_type=d.content_type,
            version=d.version,
            uploaded_by=d.uploaded_by,
            download_count=dl_count,
            published_at=d.published_at,
            created_at=d.created_at,
            updated_at=d.updated_at,
        ))

    return items, total


async def get_kb_document_detail(db: AsyncSession, doc_id: int) -> KBDocumentResponse:
    result = await db.execute(
        select(KBDocument)
        .options(joinedload(KBDocument.uploader))
        .where(KBDocument.id == doc_id, KBDocument.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(code="KB_DOCUMENT_NOT_FOUND", message="Knowledge Base document not found")

    dl_count_result = await db.execute(
        select(func.count(KBDownloadLog.id)).where(KBDownloadLog.document_id == doc.id)
    )
    dl_count = dl_count_result.scalar() or 0

    return KBDocumentResponse(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        description=doc.description,
        file_name=doc.file_name,
        file_url=doc.file_url,
        file_size=doc.file_size,
        content_type=doc.content_type,
        version=doc.version,
        uploaded_by=doc.uploaded_by,
        uploader_name=doc.uploader.full_name if doc.uploader else None,
        download_count=dl_count,
        published_at=doc.published_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def update_kb_document(
    db: AsyncSession, doc_id: int, data: KBDocumentUpdateRequest, admin_user: User,
    new_file_info: Optional[dict] = None,
) -> KBDocumentResponse:
    result = await db.execute(
        select(KBDocument).where(KBDocument.id == doc_id, KBDocument.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(code="KB_DOCUMENT_NOT_FOUND", message="Knowledge Base document not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(doc, key, value)

    if new_file_info:
        old_doc = KBDocument(
            title=doc.title,
            category=doc.category,
            description=doc.description,
            file_name=doc.file_name,
            file_url=doc.file_url,
            file_size=doc.file_size,
            content_type=doc.content_type,
            version=doc.version,
            uploaded_by=doc.uploaded_by,
            is_archived=1,
            previous_version_id=doc.previous_version_id,
        )
        db.add(old_doc)
        await db.flush()

        doc.file_name = new_file_info["file_name"]
        doc.file_url = new_file_info["file_url"]
        doc.file_size = new_file_info.get("file_size")
        doc.content_type = new_file_info.get("content_type")
        doc.version += 1
        doc.previous_version_id = old_doc.id

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "kb_document", doc.id, update_data)

    return await get_kb_document_detail(db, doc.id)


async def delete_kb_document(db: AsyncSession, doc_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(KBDocument).where(KBDocument.id == doc_id, KBDocument.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(code="KB_DOCUMENT_NOT_FOUND", message="Knowledge Base document not found")

    doc.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await write_audit_log(db, admin_user.id, "DELETE", "kb_document", doc.id, {"title": doc.title})


async def log_download(db: AsyncSession, doc_id: int, user_id: int) -> None:
    log = KBDownloadLog(document_id=doc_id, user_id=user_id)
    db.add(log)
    await db.flush()


async def get_categories(db: AsyncSession) -> list[KBCategoryResponse]:
    result = await db.execute(
        select(KBDocument.category, func.count(KBDocument.id).label("count"))
        .where(KBDocument.deleted_at.is_(None), KBDocument.is_archived == 0)
        .group_by(KBDocument.category)
        .order_by(KBDocument.category)
    )
    rows = result.all()
    return [KBCategoryResponse(name=row[0], document_count=row[1]) for row in rows]
