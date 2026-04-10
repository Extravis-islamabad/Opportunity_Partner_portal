from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.doc_request import DocRequest, DocRequestStatus, DocRequestUrgency
from app.models.user import User
from app.models.company import Company
from app.models.kb_document import KBDocument
from app.schemas.doc_request import (
    DocRequestCreateRequest,
    DocRequestFulfillRequest,
    DocRequestDeclineRequest,
    DocRequestResponse,
)
from app.core.exceptions import NotFoundException, BadRequestException
from app.utils.audit import write_audit_log
from app.services.notification_service import notify_all_admins, notify_user


async def create_doc_request(
    db: AsyncSession, data: DocRequestCreateRequest, partner_user: User
) -> DocRequestResponse:
    if not partner_user.company_id:
        raise BadRequestException(code="NO_COMPANY", message="Partner must belong to a company")

    request = DocRequest(
        company_id=partner_user.company_id,
        requested_by=partner_user.id,
        description=data.description,
        reason=data.reason,
        urgency=DocRequestUrgency(data.urgency),
    )
    db.add(request)
    await db.flush()

    await write_audit_log(db, partner_user.id, "CREATE", "doc_request", request.id, {
        "description": data.description,
    })

    company_result = await db.execute(select(Company).where(Company.id == partner_user.company_id))
    company = company_result.scalar_one_or_none()
    company_name = company.name if company else "Unknown"

    await notify_all_admins(
        db, "document_requested",
        "Document Request",
        f"{company_name} has requested a document: {data.description}",
        "doc_request", request.id,
    )

    return DocRequestResponse(
        id=request.id,
        company_id=request.company_id,
        company_name=company_name,
        requested_by=request.requested_by,
        requester_name=partner_user.full_name,
        requester_email=partner_user.email,
        description=request.description,
        reason=request.reason,
        urgency=request.urgency.value,
        status=request.status.value,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


async def get_doc_requests(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    requested_by: Optional[int] = None,
) -> tuple[list, int]:
    query = (
        select(DocRequest)
        .options(
            joinedload(DocRequest.company),
            joinedload(DocRequest.requested_by_user),
        )
        .where(DocRequest.deleted_at.is_(None))
    )
    count_query = select(func.count(DocRequest.id)).where(DocRequest.deleted_at.is_(None))

    if status:
        query = query.where(DocRequest.status == status)
        count_query = count_query.where(DocRequest.status == status)
    if company_id:
        query = query.where(DocRequest.company_id == company_id)
        count_query = count_query.where(DocRequest.company_id == company_id)
    if requested_by:
        query = query.where(DocRequest.requested_by == requested_by)
        count_query = count_query.where(DocRequest.requested_by == requested_by)

    query = query.order_by(DocRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    requests = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = [
        DocRequestResponse(
            id=r.id,
            company_id=r.company_id,
            company_name=r.company.name if r.company else None,
            requested_by=r.requested_by,
            requester_name=r.requested_by_user.full_name if r.requested_by_user else None,
            requester_email=r.requested_by_user.email if r.requested_by_user else None,
            description=r.description,
            reason=r.reason,
            urgency=r.urgency.value,
            status=r.status.value,
            fulfilled_by=r.fulfilled_by,
            fulfilled_at=r.fulfilled_at,
            fulfilled_file_url=r.fulfilled_file_url,
            fulfilled_file_name=r.fulfilled_file_name,
            decline_reason=r.decline_reason,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in requests
    ]

    return items, total


async def get_doc_request_detail(db: AsyncSession, request_id: int) -> DocRequestResponse:
    result = await db.execute(
        select(DocRequest)
        .options(
            joinedload(DocRequest.company),
            joinedload(DocRequest.requested_by_user),
            joinedload(DocRequest.fulfilled_by_user),
        )
        .where(DocRequest.id == request_id, DocRequest.deleted_at.is_(None))
    )
    r = result.scalar_one_or_none()
    if not r:
        raise NotFoundException(code="DOC_REQUEST_NOT_FOUND", message="Document request not found")

    return DocRequestResponse(
        id=r.id,
        company_id=r.company_id,
        company_name=r.company.name if r.company else None,
        requested_by=r.requested_by,
        requester_name=r.requested_by_user.full_name if r.requested_by_user else None,
        requester_email=r.requested_by_user.email if r.requested_by_user else None,
        description=r.description,
        reason=r.reason,
        urgency=r.urgency.value,
        status=r.status.value,
        fulfilled_by=r.fulfilled_by,
        fulfiller_name=r.fulfilled_by_user.full_name if r.fulfilled_by_user else None,
        fulfilled_at=r.fulfilled_at,
        fulfilled_file_url=r.fulfilled_file_url,
        fulfilled_file_name=r.fulfilled_file_name,
        decline_reason=r.decline_reason,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def fulfill_doc_request(
    db: AsyncSession,
    request_id: int,
    file_info: dict,
    data: DocRequestFulfillRequest,
    admin_user: User,
) -> DocRequestResponse:
    result = await db.execute(
        select(DocRequest).where(DocRequest.id == request_id, DocRequest.deleted_at.is_(None))
    )
    request = result.scalar_one_or_none()
    if not request:
        raise NotFoundException(code="DOC_REQUEST_NOT_FOUND", message="Document request not found")

    if request.status != DocRequestStatus.PENDING:
        raise BadRequestException(code="ALREADY_PROCESSED", message="This request has already been processed")

    request.status = DocRequestStatus.FULFILLED
    request.fulfilled_by = admin_user.id
    request.fulfilled_at = datetime.now(timezone.utc)
    request.fulfilled_file_url = file_info["file_url"]
    request.fulfilled_file_name = file_info["file_name"]

    if data.add_to_kb:
        request.add_to_kb = 1
        kb_doc = KBDocument(
            title=data.kb_title or request.description,
            category=data.kb_category or "Requested Documents",
            description=f"Fulfilled document request from company ID {request.company_id}",
            file_name=file_info["file_name"],
            file_url=file_info["file_url"],
            file_size=file_info.get("file_size"),
            content_type=file_info.get("content_type"),
            uploaded_by=admin_user.id,
        )
        db.add(kb_doc)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "doc_request", request.id, {
        "action": "fulfilled", "add_to_kb": data.add_to_kb,
    })

    await notify_user(
        db, request.requested_by, "document_request_fulfilled",
        "Document Request Fulfilled",
        f"Your document request has been fulfilled: {request.description}",
        "doc_request", request.id,
    )

    return await get_doc_request_detail(db, request.id)


async def decline_doc_request(
    db: AsyncSession, request_id: int, data: DocRequestDeclineRequest, admin_user: User
) -> DocRequestResponse:
    result = await db.execute(
        select(DocRequest).where(DocRequest.id == request_id, DocRequest.deleted_at.is_(None))
    )
    request = result.scalar_one_or_none()
    if not request:
        raise NotFoundException(code="DOC_REQUEST_NOT_FOUND", message="Document request not found")

    if request.status != DocRequestStatus.PENDING:
        raise BadRequestException(code="ALREADY_PROCESSED", message="This request has already been processed")

    request.status = DocRequestStatus.DECLINED
    request.decline_reason = data.decline_reason
    await db.flush()

    await write_audit_log(db, admin_user.id, "UPDATE", "doc_request", request.id, {
        "action": "declined", "reason": data.decline_reason,
    })

    await notify_user(
        db, request.requested_by, "document_request_declined",
        "Document Request Declined",
        f"Your document request has been declined: {request.description}. Reason: {data.decline_reason}",
        "doc_request", request.id,
    )

    return await get_doc_request_detail(db, request.id)
