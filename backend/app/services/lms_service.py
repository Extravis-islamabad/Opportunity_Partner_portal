from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.course import Course, CourseStatus
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.schemas.lms import (
    CourseCreateRequest,
    CourseUpdateRequest,
    CourseResponse,
    EnrollmentResponse,
    EnrollmentUpdateRequest,
)
from app.core.exceptions import NotFoundException, BadRequestException, ConflictException
from app.utils.audit import write_audit_log
from app.services.notification_service import notify_all_admins, notify_channel_manager, notify_user
from app.utils.email import send_template_email
from app.models.company import Company


async def create_course(db: AsyncSession, data: CourseCreateRequest, admin_user: User) -> CourseResponse:
    course = Course(
        title=data.title,
        description=data.description,
        modules_json=[m.model_dump() for m in data.modules_json],
        duration_hours=data.duration_hours,
        status=CourseStatus(data.status),
        created_by=admin_user.id,
    )
    db.add(course)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "course", course.id, {"title": data.title})

    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        status=course.status.value,
        modules_json=course.modules_json or [],
        duration_hours=course.duration_hours,
        thumbnail_url=course.thumbnail_url,
        enrollment_count=0,
        completion_count=0,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


async def get_courses(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_unpublished: bool = False,
) -> tuple[list, int]:
    query = select(Course).where(Course.deleted_at.is_(None))
    count_query = select(func.count(Course.id)).where(Course.deleted_at.is_(None))

    if not include_unpublished:
        query = query.where(Course.status == CourseStatus.PUBLISHED)
        count_query = count_query.where(Course.status == CourseStatus.PUBLISHED)
    elif status:
        query = query.where(Course.status == status)
        count_query = count_query.where(Course.status == status)

    if search:
        sf = Course.title.ilike(f"%{search}%")
        query = query.where(sf)
        count_query = count_query.where(sf)

    query = query.order_by(Course.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    courses = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for c in courses:
        enroll_count_result = await db.execute(
            select(func.count(Enrollment.id)).where(Enrollment.course_id == c.id)
        )
        enroll_count = enroll_count_result.scalar() or 0

        complete_count_result = await db.execute(
            select(func.count(Enrollment.id)).where(
                Enrollment.course_id == c.id,
                Enrollment.status == EnrollmentStatus.COMPLETED,
            )
        )
        complete_count = complete_count_result.scalar() or 0

        items.append(CourseResponse(
            id=c.id,
            title=c.title,
            description=c.description,
            status=c.status.value,
            modules_json=c.modules_json or [],
            duration_hours=c.duration_hours,
            thumbnail_url=c.thumbnail_url,
            enrollment_count=enroll_count,
            completion_count=complete_count,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ))

    return items, total


async def get_course_detail(db: AsyncSession, course_id: int) -> CourseResponse:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    enroll_count_result = await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.course_id == course.id)
    )
    enroll_count = enroll_count_result.scalar() or 0

    complete_count_result = await db.execute(
        select(func.count(Enrollment.id)).where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.COMPLETED,
        )
    )
    complete_count = complete_count_result.scalar() or 0

    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        status=course.status.value,
        modules_json=course.modules_json or [],
        duration_hours=course.duration_hours,
        thumbnail_url=course.thumbnail_url,
        enrollment_count=enroll_count,
        completion_count=complete_count,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


async def update_course(
    db: AsyncSession, course_id: int, data: CourseUpdateRequest, admin_user: User
) -> CourseResponse:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    update_data = data.model_dump(exclude_unset=True)
    if "modules_json" in update_data and update_data["modules_json"] is not None:
        update_data["modules_json"] = [m if isinstance(m, dict) else m.model_dump() for m in update_data["modules_json"]]
    if "status" in update_data:
        update_data["status"] = CourseStatus(update_data["status"])

    for key, value in update_data.items():
        setattr(course, key, value)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "course", course.id, {
        k: v.value if hasattr(v, 'value') else v for k, v in update_data.items()
    })

    return await get_course_detail(db, course.id)


async def delete_course(db: AsyncSession, course_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    course.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await write_audit_log(db, admin_user.id, "DELETE", "course", course.id, {"title": course.title})


async def enroll_in_course(db: AsyncSession, course_id: int, partner_user: User) -> EnrollmentResponse:
    course_result = await db.execute(
        select(Course).where(
            Course.id == course_id,
            Course.status == CourseStatus.PUBLISHED,
            Course.deleted_at.is_(None),
        )
    )
    course = course_result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found or not published")

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == partner_user.id,
            Enrollment.course_id == course_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException(code="ALREADY_ENROLLED", message="Already enrolled in this course")

    enrollment = Enrollment(
        user_id=partner_user.id,
        course_id=course_id,
        status=EnrollmentStatus.ENROLLED,
    )
    db.add(enrollment)
    await db.flush()

    await write_audit_log(db, partner_user.id, "CREATE", "enrollment", enrollment.id, {
        "course_id": course_id, "course_title": course.title,
    })

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=partner_user.full_name,
        course_id=enrollment.course_id,
        course_title=course.title,
        status=enrollment.status.value,
        certificate_requested=enrollment.certificate_requested,
        enrolled_at=enrollment.enrolled_at,
    )


async def update_enrollment(
    db: AsyncSession, enrollment_id: int, data: EnrollmentUpdateRequest, partner_user: User
) -> EnrollmentResponse:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.id == enrollment_id, Enrollment.user_id == partner_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")

    if data.status:
        enrollment.status = EnrollmentStatus(data.status)
        if enrollment.status == EnrollmentStatus.COMPLETED:
            enrollment.completed_at = datetime.now(timezone.utc)

    if data.progress_json is not None:
        enrollment.progress_json = data.progress_json

    await db.flush()

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=partner_user.full_name,
        course_id=enrollment.course_id,
        course_title=enrollment.course.title if enrollment.course else None,
        status=enrollment.status.value,
        progress_json=enrollment.progress_json,
        completed_at=enrollment.completed_at,
        certificate_requested=enrollment.certificate_requested,
        certificate_requested_at=enrollment.certificate_requested_at,
        certificate_url=enrollment.certificate_url,
        certificate_issued_at=enrollment.certificate_issued_at,
        enrolled_at=enrollment.enrolled_at,
    )


async def request_certificate(db: AsyncSession, enrollment_id: int, partner_user: User) -> EnrollmentResponse:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.id == enrollment_id, Enrollment.user_id == partner_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")

    if enrollment.status != EnrollmentStatus.COMPLETED:
        raise BadRequestException(code="COURSE_NOT_COMPLETED", message="Course must be completed before requesting a certificate")

    if enrollment.certificate_requested:
        raise BadRequestException(code="CERTIFICATE_ALREADY_REQUESTED", message="Certificate has already been requested")

    enrollment.certificate_requested = True
    enrollment.certificate_requested_at = datetime.now(timezone.utc)
    await db.flush()

    course_title = enrollment.course.title if enrollment.course else "Unknown Course"

    user_result = await db.execute(
        select(User).where(User.id == partner_user.id)
    )
    user = user_result.scalar_one()

    company_name = "Unknown"
    if user.company_id:
        from app.models.company import Company
        company_result = await db.execute(select(Company).where(Company.id == user.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company_name = company.name

    message = f"{partner_user.full_name} from {company_name} has completed: {course_title} and requested their certificate."

    await notify_all_admins(
        db, "certificate_requested",
        "Certificate Request",
        message,
        "enrollment", enrollment.id,
    )

    if user.company_id:
        await notify_channel_manager(
            db, user.company_id,
            "certificate_requested",
            "Certificate Request",
            message,
            "enrollment", enrollment.id,
        )

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=partner_user.full_name,
        course_id=enrollment.course_id,
        course_title=course_title,
        status=enrollment.status.value,
        completed_at=enrollment.completed_at,
        certificate_requested=enrollment.certificate_requested,
        certificate_requested_at=enrollment.certificate_requested_at,
        certificate_url=enrollment.certificate_url,
        certificate_issued_at=enrollment.certificate_issued_at,
        enrolled_at=enrollment.enrolled_at,
    )


async def issue_certificate(
    db: AsyncSession, enrollment_id: int, certificate_url: str, admin_user: User
) -> EnrollmentResponse:
    from app.services.certificate_service import generate_certificate_pdf
    from app.services.dashboard_service import evaluate_tier_upgrade

    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course), joinedload(Enrollment.user))
        .where(Enrollment.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")

    if not enrollment.certificate_requested:
        raise BadRequestException(code="NO_CERTIFICATE_REQUEST", message="No certificate request found for this enrollment")

    course_title = enrollment.course.title if enrollment.course else "Unknown Course"
    partner = enrollment.user

    # Generate certificate PDF
    company_name = "Unknown"
    if partner and partner.company_id:
        company_result = await db.execute(select(Company).where(Company.id == partner.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company_name = company.name

    import uuid
    import os
    import aiofiles
    from app.core.config import settings

    certificate_id = str(uuid.uuid4()).upper()[:12]
    pdf_bytes = generate_certificate_pdf(
        partner_name=partner.full_name if partner else "Partner",
        company_name=company_name,
        course_title=course_title,
        completion_date=enrollment.completed_at or datetime.now(timezone.utc),
        certificate_id=certificate_id,
    )

    # Save PDF to uploads directory
    cert_dir = os.path.join(settings.UPLOAD_DIR, "certificates")
    os.makedirs(cert_dir, exist_ok=True)
    pdf_filename = f"certificate_{enrollment_id}_{certificate_id}.pdf"
    pdf_path = os.path.join(cert_dir, pdf_filename)
    async with aiofiles.open(pdf_path, "wb") as f:
        await f.write(pdf_bytes)

    generated_url = f"/uploads/certificates/{pdf_filename}"
    enrollment.certificate_url = generated_url
    enrollment.certificate_issued_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(db, admin_user.id, "UPDATE", "enrollment", enrollment.id, {
        "action": "certificate_issued", "certificate_url": generated_url,
    })

    if partner:
        await send_template_email(
            to_emails=[partner.email],
            subject=f"Your Certificate for {course_title}",
            template_name="certificate",
            context={
                "name": partner.full_name,
                "course_name": course_title,
            },
        )

        await notify_user(
            db, partner.id, "certificate_issued",
            "Certificate Issued",
            f"Your certificate of completion for {course_title} is attached to this email.",
            "enrollment", enrollment.id,
            send_email_flag=False,
        )

    # Trigger tier upgrade evaluation
    if partner and partner.company_id:
        await evaluate_tier_upgrade(db, partner.company_id)

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=partner.full_name if partner else None,
        course_id=enrollment.course_id,
        course_title=course_title,
        status=enrollment.status.value,
        completed_at=enrollment.completed_at,
        score=enrollment.score,
        attempt_count=enrollment.attempt_count,
        certificate_requested=enrollment.certificate_requested,
        certificate_requested_at=enrollment.certificate_requested_at,
        certificate_url=enrollment.certificate_url,
        certificate_issued_at=enrollment.certificate_issued_at,
        enrolled_at=enrollment.enrolled_at,
    )


async def _auto_issue_certificate(db: AsyncSession, enrollment: Enrollment) -> None:
    """Auto-generate the completion certificate when a partner finishes a
    course. Skips the legacy 'request → admin approves → admin uploads PDF'
    flow entirely. Idempotent: returns if a cert already exists."""
    from app.services.certificate_service import generate_certificate_pdf
    from app.services.dashboard_service import evaluate_tier_upgrade
    import uuid
    import os
    import aiofiles
    from app.core.config import settings

    if enrollment.certificate_url:
        return  # already issued

    course_title = enrollment.course.title if enrollment.course else "Unknown Course"

    partner_result = await db.execute(select(User).where(User.id == enrollment.user_id))
    partner = partner_result.scalar_one_or_none()
    if not partner:
        return

    company_name = "Unknown"
    if partner.company_id:
        company_result = await db.execute(select(Company).where(Company.id == partner.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company_name = company.name

    certificate_id = str(uuid.uuid4()).upper()[:12]
    pdf_bytes = generate_certificate_pdf(
        partner_name=partner.full_name,
        company_name=company_name,
        course_title=course_title,
        completion_date=enrollment.completed_at or datetime.now(timezone.utc),
        certificate_id=certificate_id,
    )

    cert_dir = os.path.join(settings.UPLOAD_DIR, "certificates")
    os.makedirs(cert_dir, exist_ok=True)
    pdf_filename = f"certificate_{enrollment.id}_{certificate_id}.pdf"
    pdf_path = os.path.join(cert_dir, pdf_filename)
    async with aiofiles.open(pdf_path, "wb") as f:
        await f.write(pdf_bytes)

    enrollment.certificate_url = f"/uploads/certificates/{pdf_filename}"
    enrollment.certificate_issued_at = datetime.now(timezone.utc)
    enrollment.certificate_requested = True
    enrollment.certificate_requested_at = enrollment.completed_at or datetime.now(timezone.utc)
    await db.flush()

    try:
        await send_template_email(
            to_emails=[partner.email],
            subject=f"Your Certificate for {course_title}",
            template_name="certificate",
            context={"name": partner.full_name, "course_name": course_title},
        )
    except Exception:
        pass

    await notify_user(
        db, partner.id, "certificate_issued",
        "Certificate Issued",
        f"Your certificate of completion for {course_title} has been issued.",
        "enrollment", enrollment.id,
        send_email_flag=False,
    )

    if partner.company_id:
        try:
            await evaluate_tier_upgrade(db, partner.company_id)
        except Exception:
            pass


async def update_module_progress(
    db: AsyncSession, enrollment_id: int, module_id: str, current_user: User
) -> EnrollmentResponse:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")

    progress = enrollment.progress_json or {}
    progress[module_id] = True
    enrollment.progress_json = progress

    just_completed = False
    # If not already completed, check if all modules are done
    if enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.IN_PROGRESS
        course = enrollment.course
        if course and course.modules_json:
            module_ids = {str(m.get("id", "")) for m in course.modules_json if m.get("id")}
            completed_ids = {k for k, v in progress.items() if v}
            if module_ids and module_ids.issubset(completed_ids):
                enrollment.status = EnrollmentStatus.COMPLETED
                enrollment.completed_at = datetime.now(timezone.utc)
                just_completed = True

    await db.flush()

    if just_completed:
        await _auto_issue_certificate(db, enrollment)

    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=current_user.full_name,
        course_id=enrollment.course_id,
        course_title=enrollment.course.title if enrollment.course else None,
        status=enrollment.status.value,
        progress_json=enrollment.progress_json,
        completed_at=enrollment.completed_at,
        score=enrollment.score,
        attempt_count=enrollment.attempt_count,
        certificate_requested=enrollment.certificate_requested,
        certificate_requested_at=enrollment.certificate_requested_at,
        certificate_url=enrollment.certificate_url,
        certificate_issued_at=enrollment.certificate_issued_at,
        enrolled_at=enrollment.enrolled_at,
    )


async def submit_assessment(
    db: AsyncSession, enrollment_id: int, answers: dict, current_user: User
) -> dict:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")

    course = enrollment.course
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    assessment = course.assessment_json if course.assessment_json else []
    if not assessment:
        raise BadRequestException(code="NO_ASSESSMENT", message="No assessment available for this course")

    # Score calculation
    total_points = 0
    earned_points = 0
    for question in assessment:
        total_points += question.get("points", 1)
        if answers.get(str(question["id"])) == question.get("correct_answer"):
            earned_points += question.get("points", 1)

    score = int((earned_points / total_points) * 100) if total_points > 0 else 0
    enrollment.score = score
    enrollment.attempt_count = (enrollment.attempt_count or 0) + 1

    passing_score = course.passing_score or 70
    just_completed = False
    if score >= passing_score and enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.COMPLETED
        enrollment.completed_at = datetime.now(timezone.utc)
        just_completed = True

    await db.flush()

    if just_completed:
        await _auto_issue_certificate(db, enrollment)

    return {
        "score": score,
        "passed": score >= passing_score,
        "passing_score": passing_score,
        "attempt_count": enrollment.attempt_count,
    }


async def get_my_enrollments(
    db: AsyncSession, user_id: int
) -> list[EnrollmentResponse]:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.user_id == user_id)
        .order_by(Enrollment.enrolled_at.desc())
    )
    enrollments = result.unique().scalars().all()

    return [
        EnrollmentResponse(
            id=e.id,
            user_id=e.user_id,
            course_id=e.course_id,
            course_title=e.course.title if e.course else None,
            status=e.status.value,
            progress_json=e.progress_json,
            completed_at=e.completed_at,
            score=e.score,
            attempt_count=e.attempt_count,
            certificate_requested=e.certificate_requested,
            certificate_requested_at=e.certificate_requested_at,
            certificate_url=e.certificate_url,
            certificate_issued_at=e.certificate_issued_at,
            enrolled_at=e.enrolled_at,
        )
        for e in enrollments
    ]


async def get_enrollment_requests(
    db: AsyncSession,
    certificate_requested: bool = True,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list, int]:
    query = (
        select(Enrollment)
        .options(joinedload(Enrollment.course), joinedload(Enrollment.user))
        .where(Enrollment.certificate_requested == certificate_requested)
    )
    count_query = select(func.count(Enrollment.id)).where(
        Enrollment.certificate_requested == certificate_requested
    )

    if certificate_requested:
        query = query.where(Enrollment.certificate_url.is_(None))
        count_query = count_query.where(Enrollment.certificate_url.is_(None))

    query = query.order_by(Enrollment.certificate_requested_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    enrollments = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = [
        EnrollmentResponse(
            id=e.id,
            user_id=e.user_id,
            user_name=e.user.full_name if e.user else None,
            course_id=e.course_id,
            course_title=e.course.title if e.course else None,
            status=e.status.value,
            completed_at=e.completed_at,
            score=e.score,
            attempt_count=e.attempt_count,
            certificate_requested=e.certificate_requested,
            certificate_requested_at=e.certificate_requested_at,
            certificate_url=e.certificate_url,
            certificate_issued_at=e.certificate_issued_at,
            enrolled_at=e.enrolled_at,
        )
        for e in enrollments
    ]

    return items, total
