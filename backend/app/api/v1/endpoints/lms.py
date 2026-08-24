from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin, get_current_partner
from app.models.user import User, UserRole
from app.schemas.lms import (
    CourseCreateRequest,
    CourseUpdateRequest,
    CourseResponse,
    EnrollmentResponse,
    EnrollmentUpdateRequest,
    ModuleProgressRequest,
    AssessmentSubmitRequest,
    AssessmentResultResponse,
)
from app.schemas.common import MessageResponse
from app.services import lms_service

router = APIRouter(prefix="/lms", tags=["LMS"])


@router.put("/enrollments/{enrollment_id}/progress", response_model=EnrollmentResponse, status_code=200)
async def update_module_progress(
    enrollment_id: int,
    data: ModuleProgressRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.update_module_progress(db, enrollment_id, data.module_id, partner)


@router.post("/enrollments/{enrollment_id}/submit-assessment", response_model=AssessmentResultResponse, status_code=200)
async def submit_assessment(
    enrollment_id: int,
    data: AssessmentSubmitRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.submit_assessment(db, enrollment_id, data.answers, partner)
