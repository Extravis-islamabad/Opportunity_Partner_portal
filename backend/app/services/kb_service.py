from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings
from app.models.kb_document import KBDocument, KBDownloadLog
from app.utils.file_tokens import signed_file_url
from app.models.user import User
from app.schemas.knowledge_base import (
    KBDocumentCreateRequest,
    KBDocumentUpdateRequest,
    KBDocumentResponse,
    KBCategoryResponse,
    KB_CANONICAL_CATEGORIES,
    KB_REQUESTED_DOCUMENTS_CATEGORY,
)
from app.core.exceptions import NotFoundException, UnprocessableException
from app.utils.audit import write_audit_log


async def validate_category(db: AsyncSession, category: str) -> str:
    """Return the category to store, or raise a 422.

    Accepted: the canonical list the upload forms offer (matched
    case-insensitively and normalised to its canonical spelling, so "patchx"
    doesn't fork a second PatchX bucket), the fulfilment default, and any
    category a live document already uses — the seeded/legacy ones such as
    "Sales" or "Battlecards" — so those documents stay editable without
    forcing a recategorisation. Anything else is a typo or an attempt to mint
    a new category through the API, which the UI never offers.
    """
    lowered = category.strip().lower()
    for canonical in (*KB_CANONICAL_CATEGORIES, KB_REQUESTED_DOCUMENTS_CATEGORY):
        if canonical.lower() == lowered:
            return canonical

    in_use = await db.execute(
        select(KBDocument.category).where(
            KBDocument.deleted_at.is_(None),
            func.lower(KBDocument.category) == lowered,
        ).limit(1)
    )
    existing = in_use.scalar_one_or_none()
    if existing is not None:
        return existing

    raise UnprocessableException(
        code="INVALID_KB_CATEGORY",
        message=f"Unknown Knowledge Base category '{category}'",
        details={"allowed_categories": list(KB_CANONICAL_CATEGORIES)},
    )


def _stored_file_ref(file_url: str) -> str:
    """The raw '/uploads/...' path for a row.

    Archived versions written before the versioning fix stored an already
    signed '/api/v1/files/download?token=...' URL instead of the path. Re-
    signing that produced a token for a nonsense path (and the embedded token
    expired after 30 minutes anyway), so old versions 404'd. Recover the path
    from the embedded token, ignoring its expiry — we only trust the signature
    to tell us which file it named, and access is re-authorised by the caller.
    """
    marker = "/api/v1/files/download?token="
    if not file_url.startswith(marker):
        return file_url
    try:
        payload = jwt.decode(
            file_url[len(marker):], settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM], options={"verify_exp": False},
        )
    except JWTError:
        return file_url
    fp = payload.get("fp")
    return f"/uploads/{fp}" if isinstance(fp, str) and fp else file_url


def _to_response(
    doc: KBDocument, *, download_count: int = 0, uploader_name: Optional[str] = None,
) -> KBDocumentResponse:
    # file_url deliberately left out: only the download endpoint mints one,
    # so every download goes through the log.
    return KBDocumentResponse(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        description=doc.description,
        file_name=doc.file_name,
        file_size=doc.file_size,
        content_type=doc.content_type,
        version=doc.version,
        previous_version_id=doc.previous_version_id,
        is_archived=bool(doc.is_archived),
        uploaded_by=doc.uploaded_by,
        uploader_name=uploader_name,
        download_count=download_count,
        published_at=doc.published_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


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

    return _to_response(doc, uploader_name=admin_user.full_name)


async def get_kb_documents(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list, int]:
    # Archived rows are superseded versions, never "current" documents.
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
        items.append(_to_response(d, download_count=dl_count))

    return items, total


async def _load_document(
    db: AsyncSession, doc_id: int, include_archived: bool = False,
) -> KBDocument:
    query = (
        select(KBDocument)
        .options(joinedload(KBDocument.uploader))
        .where(KBDocument.id == doc_id, KBDocument.deleted_at.is_(None))
    )
    if not include_archived:
        # Superseded versions are only reachable by admins (who follow
        # previous_version_id to them); to everyone else they don't exist.
        query = query.where(KBDocument.is_archived == 0)
    doc = (await db.execute(query)).scalar_one_or_none()
    if not doc:
        raise NotFoundException(code="KB_DOCUMENT_NOT_FOUND", message="Knowledge Base document not found")
    return doc


async def get_kb_document_detail(
    db: AsyncSession, doc_id: int, include_archived: bool = False,
) -> KBDocumentResponse:
    doc = await _load_document(db, doc_id, include_archived)

    dl_count_result = await db.execute(
        select(func.count(KBDownloadLog.id)).where(KBDownloadLog.document_id == doc.id)
    )
    dl_count = dl_count_result.scalar() or 0

    return _to_response(
        doc, download_count=dl_count,
        uploader_name=doc.uploader.full_name if doc.uploader else None,
    )


async def get_download_link(
    db: AsyncSession, doc_id: int, user_id: int, include_archived: bool = False,
) -> dict:
    """The only place a KB file URL is minted — and it logs the download in
    the same breath, so the count can't be sidestepped."""
    doc = await _load_document(db, doc_id, include_archived)
    await log_download(db, doc.id, user_id)
    return {
        "file_url": signed_file_url(_stored_file_ref(doc.file_url)),
        "file_name": doc.file_name,
    }


async def update_kb_document(
    db: AsyncSession, doc_id: int, data: KBDocumentUpdateRequest, admin_user: User,
    new_file_info: Optional[dict] = None,
) -> KBDocumentResponse:
    # Only current versions are editable; an archived row is history.
    doc = await _load_document(db, doc_id)

    # Snapshot the outgoing version BEFORE touching anything. Applying the
    # metadata first gave the archived row the new title, and copying a
    # signed URL into it (instead of the stored path) made the old file
    # undownloadable once the token expired.
    if new_file_info:
        old_doc = KBDocument(
            title=doc.title,
            category=doc.category,
            description=doc.description,
            file_name=doc.file_name,
            file_url=_stored_file_ref(doc.file_url),
            file_size=doc.file_size,
            content_type=doc.content_type,
            version=doc.version,
            uploaded_by=doc.uploaded_by,
            is_archived=1,
            previous_version_id=doc.previous_version_id,
            published_at=doc.published_at,
        )
        db.add(old_doc)
        await db.flush()

    # exclude_unset: a field the caller didn't send is left as it is.
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(doc, key, value)

    if new_file_info:
        doc.file_name = new_file_info["file_name"]
        doc.file_url = new_file_info["file_url"]
        doc.file_size = new_file_info.get("file_size")
        doc.content_type = new_file_info.get("content_type")
        doc.version += 1
        doc.previous_version_id = old_doc.id

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "kb_document", doc.id, {
        **update_data, **({"new_version": doc.version} if new_file_info else {}),
    })

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
