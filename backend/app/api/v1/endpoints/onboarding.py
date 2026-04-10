from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_partner
from app.models.user import User
from app.models.opportunity import Opportunity
from app.models.kb_document import KBDownloadLog
from app.models.enrollment import Enrollment
from app.models.doc_request import DocRequest
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/checklist", status_code=200)
async def get_checklist(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    opp_count = (
        await db.execute(
            select(func.count(Opportunity.id)).where(
                Opportunity.submitted_by == partner.id,
                Opportunity.deleted_at.is_(None),
            )
        )
    ).scalar() or 0

    kb_count = (
        await db.execute(
            select(func.count(KBDownloadLog.id)).where(
                KBDownloadLog.user_id == partner.id,
            )
        )
    ).scalar() or 0

    enrollment_count = (
        await db.execute(
            select(func.count(Enrollment.id)).where(
                Enrollment.user_id == partner.id,
            )
        )
    ).scalar() or 0

    doc_request_count = (
        await db.execute(
            select(func.count(DocRequest.id)).where(
                DocRequest.requested_by == partner.id,
                DocRequest.deleted_at.is_(None),
            )
        )
    ).scalar() or 0

    profile_complete = partner.job_title is not None

    items = [
        {"key": "submit_first_opportunity", "label": "Submit your first opportunity", "completed": opp_count > 0},
        {"key": "browse_knowledge_base", "label": "Browse the knowledge base", "completed": kb_count > 0},
        {"key": "enrol_in_course", "label": "Enrol in a course", "completed": enrollment_count > 0},
        {"key": "complete_profile", "label": "Complete your profile", "completed": profile_complete},
        {"key": "submit_doc_request", "label": "Submit a document request", "completed": doc_request_count > 0},
    ]

    return {
        "has_completed_onboarding": partner.has_completed_onboarding,
        "items": items,
    }


@router.post("/complete", response_model=MessageResponse, status_code=200)
async def complete_onboarding(
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    partner.has_completed_onboarding = True
    await db.flush()
    await db.commit()
    return MessageResponse(message="Onboarding marked as complete")
