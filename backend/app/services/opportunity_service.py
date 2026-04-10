from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opp_document import OppDocument
from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.opportunity import (
    OpportunityCreateRequest,
    OpportunityUpdateRequest,
    OpportunityResponse,
    OpportunityListResponse,
    OppDocumentResponse,
    OpportunityApproveRequest,
    OpportunityRejectRequest,
    OpportunityInternalNoteRequest,
)
from app.core.exceptions import NotFoundException, BadRequestException, ForbiddenException, ConflictException
from app.utils.audit import write_audit_log
from app.services.notification_service import notify_all_admins, notify_user


def _build_opportunity_response(opp: Opportunity) -> OpportunityResponse:
    return OpportunityResponse(
        id=opp.id,
        name=opp.name,
        customer_name=opp.customer_name,
        region=opp.region,
        country=opp.country,
        city=opp.city,
        worth=opp.worth,
        closing_date=opp.closing_date,
        requirements=opp.requirements,
        status=opp.status.value,
        preferred_partner=opp.preferred_partner,
        multi_partner_alert=opp.multi_partner_alert,
        rejection_reason=opp.rejection_reason,
        internal_notes=opp.internal_notes,
        submitted_by=opp.submitted_by,
        submitted_by_name=opp.submitted_by_user.full_name if opp.submitted_by_user else None,
        company_id=opp.company_id,
        company_name=opp.company.name if opp.company else None,
        reviewed_by=opp.reviewed_by,
        reviewer_name=opp.reviewer.full_name if opp.reviewer else None,
        submitted_at=opp.submitted_at,
        reviewed_at=opp.reviewed_at,
        documents=[
            OppDocumentResponse(
                id=d.id, file_name=d.file_name, file_url=d.file_url,
                file_size=d.file_size, content_type=d.content_type, uploaded_at=d.uploaded_at,
            )
            for d in (opp.documents or [])
            if d.deleted_at is None
        ],
        created_at=opp.created_at,
        updated_at=opp.updated_at,
    )


async def create_opportunity(
    db: AsyncSession, data: OpportunityCreateRequest, partner_user: User
) -> OpportunityResponse:
    opp = Opportunity(
        name=data.name,
        customer_name=data.customer_name,
        region=data.region,
        country=data.country,
        city=data.city,
        worth=data.worth,
        closing_date=data.closing_date,
        requirements=data.requirements,
        status=OpportunityStatus(data.status or "draft"),
        submitted_by=partner_user.id,
        company_id=partner_user.company_id,
    )

    if opp.status == OpportunityStatus.PENDING_REVIEW:
        opp.submitted_at = datetime.now(timezone.utc)

    db.add(opp)
    await db.flush()

    if opp.status == OpportunityStatus.PENDING_REVIEW:
        await _check_multi_partner_conflict(db, opp)

        company_result = await db.execute(select(Company).where(Company.id == partner_user.company_id))
        company = company_result.scalar_one_or_none()
        company_name = company.name if company else "Unknown"

        await notify_all_admins(
            db, "opportunity_submitted",
            "New Opportunity Submitted",
            f"{company_name} has submitted an opportunity for approval: {opp.name}",
            "opportunity", opp.id,
        )

    await write_audit_log(db, partner_user.id, "CREATE", "opportunity", opp.id, {
        "name": opp.name, "status": opp.status.value,
    })

    await db.refresh(opp, ["submitted_by_user", "company", "documents"])
    return _build_opportunity_response(opp)


async def _check_multi_partner_conflict(db: AsyncSession, opp: Opportunity) -> None:
    result = await db.execute(
        select(Opportunity).where(
            func.lower(Opportunity.customer_name) == func.lower(opp.customer_name),
            func.lower(Opportunity.name) == func.lower(opp.name),
            Opportunity.id != opp.id,
            Opportunity.company_id != opp.company_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.status != OpportunityStatus.REMOVED,
        )
    )
    conflicts = result.scalars().all()

    if conflicts:
        opp.multi_partner_alert = True
        for conflict in conflicts:
            conflict.multi_partner_alert = True

        await notify_all_admins(
            db, "multi_partner_conflict",
            "Multi-Partner Alert",
            f"[MULTI-PARTNER ALERT] Two or more partners have submitted on customer: {opp.customer_name}",
            "opportunity", opp.id,
        )


async def get_opportunities(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    company_id: Optional[int] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    submitted_by: Optional[int] = None,
    channel_manager_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[list, int]:
    query = (
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
        )
        .where(Opportunity.deleted_at.is_(None))
    )
    count_query = select(func.count(Opportunity.id)).where(Opportunity.deleted_at.is_(None))

    if status:
        query = query.where(Opportunity.status == status)
        count_query = count_query.where(Opportunity.status == status)
    if company_id:
        query = query.where(Opportunity.company_id == company_id)
        count_query = count_query.where(Opportunity.company_id == company_id)
    if country:
        query = query.where(Opportunity.country == country)
        count_query = count_query.where(Opportunity.country == country)
    if region:
        query = query.where(Opportunity.region == region)
        count_query = count_query.where(Opportunity.region == region)
    if submitted_by:
        query = query.where(Opportunity.submitted_by == submitted_by)
        count_query = count_query.where(Opportunity.submitted_by == submitted_by)
    if search:
        sf = or_(
            Opportunity.name.ilike(f"%{search}%"),
            Opportunity.customer_name.ilike(f"%{search}%"),
        )
        query = query.where(sf)
        count_query = count_query.where(sf)
    if channel_manager_id:
        query = query.join(Company, Opportunity.company_id == Company.id).where(
            Company.channel_manager_id == channel_manager_id
        )
        count_query = count_query.join(Company, Opportunity.company_id == Company.id).where(
            Company.channel_manager_id == channel_manager_id
        )

    query = query.order_by(Opportunity.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    opps = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for o in opps:
        items.append(OpportunityListResponse(
            id=o.id,
            name=o.name,
            customer_name=o.customer_name,
            country=o.country,
            worth=o.worth,
            closing_date=o.closing_date,
            status=o.status.value,
            preferred_partner=o.preferred_partner,
            multi_partner_alert=o.multi_partner_alert,
            submitted_by_name=o.submitted_by_user.full_name if o.submitted_by_user else None,
            company_name=o.company.name if o.company else None,
            company_id=o.company_id,
            submitted_at=o.submitted_at,
            created_at=o.created_at,
        ))

    return items, total


async def get_opportunity_detail(db: AsyncSession, opp_id: int) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")
    return _build_opportunity_response(opp)


async def update_opportunity(
    db: AsyncSession, opp_id: int, data: OpportunityUpdateRequest, partner_user: User
) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.submitted_by != partner_user.id:
        raise ForbiddenException(message="You can only edit your own opportunities")

    if opp.status in (OpportunityStatus.UNDER_REVIEW, OpportunityStatus.APPROVED):
        raise ConflictException(
            code="OPPORTUNITY_LOCKED",
            message="This opportunity can no longer be edited. An admin is reviewing it.",
        )

    if opp.status not in (OpportunityStatus.DRAFT, OpportunityStatus.PENDING_REVIEW, OpportunityStatus.REJECTED):
        raise BadRequestException(
            code="CANNOT_EDIT",
            message="Opportunities can only be edited in Draft, Pending Review, or Rejected status",
        )

    update_data = data.model_dump(exclude_unset=True)
    before_state = {key: getattr(opp, key) for key in update_data}
    # Convert any non-serializable values in before_state
    for key, value in before_state.items():
        if hasattr(value, 'value'):
            before_state[key] = value.value

    for key, value in update_data.items():
        setattr(opp, key, value)

    await db.flush()
    await write_audit_log(db, partner_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": update_data,
    })

    return _build_opportunity_response(opp)


async def submit_opportunity(db: AsyncSession, opp_id: int, partner_user: User) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.submitted_by != partner_user.id:
        raise ForbiddenException(message="You can only submit your own opportunities")

    if opp.status not in (OpportunityStatus.DRAFT, OpportunityStatus.REJECTED):
        raise BadRequestException(code="CANNOT_SUBMIT", message="Only Draft or Rejected opportunities can be submitted")

    before_state = {"status": opp.status.value}

    opp.status = OpportunityStatus.PENDING_REVIEW
    opp.submitted_at = datetime.now(timezone.utc)
    opp.rejection_reason = None

    await _check_multi_partner_conflict(db, opp)

    company_name = opp.company.name if opp.company else "Unknown"
    await notify_all_admins(
        db, "opportunity_submitted",
        "New Opportunity Submitted",
        f"{company_name} has submitted an opportunity for approval: {opp.name}",
        "opportunity", opp.id,
    )

    await db.flush()
    await write_audit_log(db, partner_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": {"status": "pending_review"},
    })

    return _build_opportunity_response(opp)


async def approve_opportunity(
    db: AsyncSession, opp_id: int, data: OpportunityApproveRequest, admin_user: User
) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.status not in (OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW):
        raise BadRequestException(code="CANNOT_APPROVE", message="Opportunity is not in a reviewable state")

    before_state = {"status": opp.status.value, "preferred_partner": opp.preferred_partner}

    opp.status = OpportunityStatus.APPROVED
    opp.reviewed_by = admin_user.id
    opp.reviewed_at = datetime.now(timezone.utc)
    opp.preferred_partner = data.preferred_partner

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": {"status": "approved", "preferred_partner": data.preferred_partner},
    })

    await notify_user(
        db, opp.submitted_by, "opportunity_approved",
        "Opportunity Approved",
        f"An Admin has updated the opportunity: {opp.name} — Status: Approved",
        "opportunity", opp.id,
    )

    if data.preferred_partner:
        await notify_user(
            db, opp.submitted_by, "preferred_partner_tag",
            "Preferred Partner",
            f"Congratulations! Your opportunity {opp.name} has been tagged as Preferred Partner.",
            "opportunity", opp.id,
        )

    # Evaluate tier upgrade after approval
    if opp.company_id:
        from app.services.dashboard_service import evaluate_tier_upgrade
        await evaluate_tier_upgrade(db, opp.company_id)

    return _build_opportunity_response(opp)


async def reject_opportunity(
    db: AsyncSession, opp_id: int, data: OpportunityRejectRequest, admin_user: User
) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.status not in (OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW):
        raise BadRequestException(code="CANNOT_REJECT", message="Opportunity is not in a reviewable state")

    before_state = {"status": opp.status.value, "rejection_reason": opp.rejection_reason}

    opp.status = OpportunityStatus.REJECTED
    opp.rejection_reason = data.rejection_reason
    opp.reviewed_by = admin_user.id
    opp.reviewed_at = datetime.now(timezone.utc)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": {"status": "rejected", "rejection_reason": data.rejection_reason},
    })

    await notify_user(
        db, opp.submitted_by, "opportunity_rejected",
        "Opportunity Rejected",
        f"An Admin has updated the opportunity: {opp.name} — Status: Rejected. Reason: {data.rejection_reason}",
        "opportunity", opp.id,
    )

    return _build_opportunity_response(opp)


async def remove_opportunity(db: AsyncSession, opp_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    opp.status = OpportunityStatus.REMOVED
    opp.deleted_at = datetime.now(timezone.utc)

    await db.flush()
    await write_audit_log(db, admin_user.id, "DELETE", "opportunity", opp.id, {"name": opp.name})

    await notify_user(
        db, opp.submitted_by, "opportunity_removed",
        "Opportunity Removed",
        f"An Admin has removed the opportunity: {opp.name}",
        "opportunity", opp.id,
    )


async def add_internal_note(
    db: AsyncSession, opp_id: int, data: OpportunityInternalNoteRequest, admin_user: User
) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    before_state = {"internal_notes": opp.internal_notes}

    opp.internal_notes = data.internal_notes
    await db.flush()

    await write_audit_log(db, admin_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": {"internal_notes": data.internal_notes},
    })

    await notify_user(
        db, opp.submitted_by, "internal_note_added",
        "Note Added to Opportunity",
        f"An Admin has left a note on the opportunity: {opp.name}",
        "opportunity", opp.id,
    )

    return _build_opportunity_response(opp)


async def mark_under_review(db: AsyncSession, opp_id: int, admin_user: User) -> OpportunityResponse:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.status != OpportunityStatus.PENDING_REVIEW:
        raise BadRequestException(code="CANNOT_REVIEW", message="Only pending opportunities can be marked under review")

    before_state = {"status": opp.status.value}

    opp.status = OpportunityStatus.UNDER_REVIEW
    opp.reviewed_by = admin_user.id
    await db.flush()

    await write_audit_log(db, admin_user.id, "UPDATE", "opportunity", opp.id, {
        "before": before_state,
        "after": {"status": "under_review"},
    })

    return _build_opportunity_response(opp)


async def auto_mark_under_review(
    db: AsyncSession, opp_id: int, admin_user: User
) -> OpportunityResponse:
    """Auto-transition opportunity to under_review when an admin views it."""
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.submitted_by_user),
            joinedload(Opportunity.company),
            joinedload(Opportunity.reviewer),
            joinedload(Opportunity.documents),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    if opp.status == OpportunityStatus.PENDING_REVIEW:
        before_status = opp.status.value
        opp.status = OpportunityStatus.UNDER_REVIEW
        opp.reviewed_by = admin_user.id
        await write_audit_log(db, admin_user.id, "UPDATE", "opportunity", opp.id,
                              {"before": {"status": before_status}, "after": {"status": "under_review"}})
        await db.flush()

    return _build_opportunity_response(opp)


async def add_opp_document(db: AsyncSession, opp_id: int, file_info: dict) -> OppDocumentResponse:
    # Enforce max 5 files per opportunity
    count_result = await db.execute(
        select(func.count(OppDocument.id)).where(
            OppDocument.opportunity_id == opp_id,
            OppDocument.deleted_at.is_(None),
        )
    )
    doc_count = count_result.scalar() or 0
    if doc_count >= 5:
        raise BadRequestException(
            code="MAX_DOCUMENTS_REACHED",
            message="Maximum of 5 files allowed per opportunity",
        )

    doc = OppDocument(
        opportunity_id=opp_id,
        file_name=file_info["file_name"],
        file_url=file_info["file_url"],
        file_size=file_info.get("file_size"),
        content_type=file_info.get("content_type"),
    )
    db.add(doc)
    await db.flush()
    return OppDocumentResponse(
        id=doc.id,
        file_name=doc.file_name,
        file_url=doc.file_url,
        file_size=doc.file_size,
        content_type=doc.content_type,
        uploaded_at=doc.uploaded_at,
    )


async def remove_opp_document(
    db: AsyncSession, opp_id: int, doc_id: int, current_user: User
) -> None:
    """Soft-delete a document from an opportunity."""
    # Get the opportunity
    opp_result = await db.execute(
        select(Opportunity).where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = opp_result.scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    # Partners can only delete docs from their own opportunities in editable states
    if current_user.role == UserRole.PARTNER:
        if opp.submitted_by != current_user.id:
            raise ForbiddenException(message="You can only modify your own opportunities")
        if opp.status not in (OpportunityStatus.PENDING_REVIEW, OpportunityStatus.UNDER_REVIEW):
            raise BadRequestException(
                code="CANNOT_DELETE_DOCUMENT",
                message="Documents can only be removed while the opportunity is pending or under review",
            )

    # Get the document
    doc_result = await db.execute(
        select(OppDocument).where(
            OppDocument.id == doc_id,
            OppDocument.opportunity_id == opp_id,
            OppDocument.deleted_at.is_(None),
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(code="DOCUMENT_NOT_FOUND", message="Document not found")

    doc.deleted_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(db, current_user.id, "DELETE", "opp_document", doc.id, {
        "opportunity_id": opp_id,
        "file_name": doc.file_name,
    })
