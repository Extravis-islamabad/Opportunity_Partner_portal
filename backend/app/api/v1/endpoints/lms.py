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


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    data: CourseCreateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.create_course(db, data, admin)


@router.get("/courses", status_code=200)
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    include_unpublished = current_user.role == UserRole.ADMIN
    items, total = await lms_service.get_courses(
        db, page, page_size, status, search, include_unpublished
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/courses/{course_id}", response_model=CourseResponse, status_code=200)
async def get_course(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.get_course_detail(db, course_id)


@router.put("/courses/{course_id}", response_model=CourseResponse, status_code=200)
async def update_course(
    course_id: int,
    data: CourseUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.update_course(db, course_id, data, admin)


@router.delete("/courses/{course_id}", response_model=MessageResponse, status_code=200)
async def delete_course(
    course_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await lms_service.delete_course(db, course_id, admin)
    return MessageResponse(message="Course deleted successfully")


@router.post("/courses/{course_id}/enroll", response_model=EnrollmentResponse, status_code=201)
async def enroll_in_course(
    course_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.enroll_in_course(db, course_id, partner)


@router.get("/enrollments/me", status_code=200)
async def my_enrollments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.get_my_enrollments(db, current_user.id)


@router.put("/enrollments/{enrollment_id}", response_model=EnrollmentResponse, status_code=200)
async def update_enrollment(
    enrollment_id: int,
    data: EnrollmentUpdateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.update_enrollment(db, enrollment_id, data, partner)


@router.post("/enrollments/{enrollment_id}/request-certificate", response_model=EnrollmentResponse, status_code=200)
async def request_certificate(
    enrollment_id: int,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.request_certificate(db, enrollment_id, partner)


@router.get("/certificate-requests", status_code=200)
async def list_certificate_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    items, total = await lms_service.get_enrollment_requests(db, True, page, page_size)
    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/enrollments/{enrollment_id}/issue-certificate", response_model=EnrollmentResponse, status_code=200)
async def issue_certificate(
    enrollment_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await lms_service.issue_certificate(db, enrollment_id, "", admin)


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
