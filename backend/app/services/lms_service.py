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
from app.utils.file_tokens import signed_file_url
from app.services.notification_service import notify_all_admins, notify_channel_manager, notify_user
from app.utils.email import send_template_email
from app.models.company import Company


def _public_assessment(assessment) -> list:
    """The quiz as a non-admin may see it: everything but the answer key.

    submit_assessment scores against `correct_answer` (and the frontend once
    read a legacy `correct` alias), so either one reaching a partner's browser
    lets them pass without knowing anything."""
    if not isinstance(assessment, list):
        return []
    return [
        {k: v for k, v in q.items() if k not in ("correct_answer", "correct")}
        for q in assessment
        if isinstance(q, dict)
    ]


def _course_response(
    course: Course, enroll_count: int, complete_count: int, include_answer_key: bool
) -> CourseResponse:
    assessment = course.assessment_json or []
    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        status=course.status.value,
        modules_json=course.modules_json or [],
        assessment_json=assessment if include_answer_key else _public_assessment(assessment),
        passing_score=course.passing_score if course.passing_score is not None else 70,
        duration_hours=course.duration_hours,
        thumbnail_url=course.thumbnail_url,
        enrollment_count=enroll_count,
        completion_count=complete_count,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


async def _enrollment_counts(db: AsyncSession, course_id: int) -> tuple[int, int]:
    enroll_count = (await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.course_id == course_id)
    )).scalar() or 0
    complete_count = (await db.execute(
        select(func.count(Enrollment.id)).where(
            Enrollment.course_id == course_id,
            Enrollment.status == EnrollmentStatus.COMPLETED,
        )
    )).scalar() or 0
    return enroll_count, complete_count


async def create_course(db: AsyncSession, data: CourseCreateRequest, admin_user: User) -> CourseResponse:
    course = Course(
        title=data.title,
        description=data.description,
        modules_json=[m.model_dump() for m in data.modules_json],
        assessment_json=[q.model_dump() for q in data.assessment_json],
        passing_score=data.passing_score,
        duration_hours=data.duration_hours,
        status=CourseStatus(data.status),
        created_by=admin_user.id,
    )
    db.add(course)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "course", course.id, {"title": data.title})

    return _course_response(course, 0, 0, include_answer_key=True)


async def get_courses(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_unpublished: bool = False,
    include_answer_key: bool = False,
) -> tuple[list, int]:
    query = select(Course).where(Course.deleted_at.is_(None))
    count_query = select(func.count(Course.id)).where(Course.deleted_at.is_(None))

    if not include_unpublished:
        query = query.where(Course.status == CourseStatus.PUBLISHED)
        count_query = count_query.where(Course.status == CourseStatus.PUBLISHED)
    elif status:
        # The route already pattern-checks this; converting here as well means
        # a direct caller with a bad value gets a ValueError (400), not a
        # database enum error.
        course_status = CourseStatus(status)
        query = query.where(Course.status == course_status)
        count_query = count_query.where(Course.status == course_status)

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
        enroll_count, complete_count = await _enrollment_counts(db, c.id)
        items.append(_course_response(c, enroll_count, complete_count, include_answer_key))

    return items, total


async def get_course_detail(
    db: AsyncSession,
    course_id: int,
    include_unpublished: bool = False,
    include_answer_key: bool = False,
) -> CourseResponse:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    # Non-admins may only see published courses. Return 404 (not 403) for a
    # draft so its existence isn't confirmed — mirrors the list route, which
    # filters unpublished out for non-admins.
    if not include_unpublished and course.status != CourseStatus.PUBLISHED:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    enroll_count, complete_count = await _enrollment_counts(db, course.id)
    return _course_response(course, enroll_count, complete_count, include_answer_key)


async def update_course(
    db: AsyncSession, course_id: int, data: CourseUpdateRequest, admin_user: User
) -> CourseResponse:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException(code="COURSE_NOT_FOUND", message="Course not found")

    # The schema has already refused explicit nulls for the fields that can't
    # hold one, so everything set here is a real value.
    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = CourseStatus(update_data["status"])

    for key, value in update_data.items():
        setattr(course, key, value)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "course", course.id, {
        k: v.value if hasattr(v, 'value') else v for k, v in update_data.items()
    })

    # Only admins reach this, and the course may be (or have just become) a
    # draft — reading it back through the partner view 404'd every edit of an
    # unpublished course, including the unpublish itself.
    return await get_course_detail(
        db, course.id, include_unpublished=True, include_answer_key=True
    )


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
        enrolled_at=enrollment.enrolled_at,
    )


def _progress_of(enrollment: Enrollment) -> dict:
    """The enrolment's progress map, or {} if the stored value isn't one.

    PUT /enrollments once stored whatever JSON it was sent, so rows exist with
    a string or list here; treating those as "nothing done yet" keeps them
    usable instead of 500ing every later progress update."""
    progress = enrollment.progress_json
    return dict(progress) if isinstance(progress, dict) else {}


def _module_ids(course: Course, *, quiz: bool) -> set[str]:
    return {
        str(m.get("id"))
        for m in (course.modules_json or [])
        if isinstance(m, dict) and m.get("id") and (m.get("type") == "quiz") == quiz
    }


def _quiz_passed(course: Course, enrollment: Enrollment) -> bool:
    passing_score = course.passing_score or 70
    return enrollment.score is not None and enrollment.score >= passing_score


def _completion_requirements_met(course: Course, enrollment: Enrollment) -> bool:
    """The one definition of "finished this course", shared by every path
    that can complete an enrolment — completion feeds the company's tier and
    issues a certificate, so no path may be laxer than the others.

    Every non-quiz lesson must be marked done, and if the course has quiz
    questions the best score must clear the pass mark. Quiz *modules* are only
    placeholders for where the quiz sits in the sequence, so they are never a
    requirement in their own right (and can't be ticked off via /progress)."""
    done = {k for k, v in _progress_of(enrollment).items() if v}
    if not _module_ids(course, quiz=False).issubset(done):
        return False
    if course.assessment_json and not _quiz_passed(course, enrollment):
        return False
    return True


def _ensure_course_open(course: Optional[Course]) -> Course:
    # An enrolment outlives its course being unpublished or deleted, but
    # progress on it must not keep accruing — finishing a withdrawn course
    # would still count towards tier and mint a certificate.
    if not course or course.deleted_at is not None or course.status != CourseStatus.PUBLISHED:
        raise BadRequestException(
            code="COURSE_UNAVAILABLE",
            message="This course is no longer available",
        )
    return course


async def _own_enrollment(db: AsyncSession, enrollment_id: int, user: User) -> Enrollment:
    result = await db.execute(
        select(Enrollment)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.id == enrollment_id, Enrollment.user_id == user.id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException(code="ENROLLMENT_NOT_FOUND", message="Enrollment not found")
    return enrollment


def _complete(enrollment: Enrollment) -> None:
    enrollment.status = EnrollmentStatus.COMPLETED
    enrollment.completed_at = datetime.now(timezone.utc)


def _enrollment_response(enrollment: Enrollment, user_name: Optional[str] = None) -> EnrollmentResponse:
    return EnrollmentResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        user_name=user_name,
        course_id=enrollment.course_id,
        course_title=enrollment.course.title if enrollment.course else None,
        status=enrollment.status.value,
        progress_json=enrollment.progress_json,
        completed_at=enrollment.completed_at,
        score=enrollment.score,
        attempt_count=enrollment.attempt_count or 0,
        certificate_url=signed_file_url(enrollment.certificate_url),
        certificate_issued_at=enrollment.certificate_issued_at,
        enrolled_at=enrollment.enrolled_at,
    )


async def update_enrollment(
    db: AsyncSession, enrollment_id: int, data: EnrollmentUpdateRequest, partner_user: User
) -> EnrollmentResponse:
    enrollment = await _own_enrollment(db, enrollment_id, partner_user)
    course = _ensure_course_open(enrollment.course)

    # Writing the progress map wholesale let a partner tick off every lesson
    # (and the quiz) in one request. Progress goes through /progress instead.
    if data.progress_json is not None:
        raise BadRequestException(
            code="PROGRESS_READ_ONLY",
            message="Progress is recorded per lesson via /progress, not set directly",
        )

    just_completed = False
    if data.status:
        requested = EnrollmentStatus(data.status)
        if enrollment.status == EnrollmentStatus.COMPLETED:
            # Completion is what tier and the certificate rest on; it is not
            # something to toggle back off. Re-asserting it is a no-op.
            if requested != EnrollmentStatus.COMPLETED:
                raise BadRequestException(
                    code="ENROLLMENT_COMPLETED",
                    message="A completed enrolment cannot be moved back",
                )
        elif requested == EnrollmentStatus.COMPLETED:
            # Granted only if the work is genuinely done — this is how a
            # course with nothing to tick off (no lessons, no quiz) gets
            # finished, and must not be a shortcut past the lessons or quiz.
            if not _completion_requirements_met(course, enrollment):
                raise BadRequestException(
                    code="COMPLETION_REQUIREMENTS_NOT_MET",
                    message="Finish every lesson and pass the quiz to complete this course",
                )
            _complete(enrollment)
            just_completed = True
        else:
            enrollment.status = requested

    await db.flush()

    if just_completed:
        await _auto_issue_certificate(db, enrollment)

    return _enrollment_response(enrollment, partner_user.full_name)


async def _auto_issue_certificate(db: AsyncSession, enrollment: Enrollment) -> None:
    """Auto-generate the completion certificate when a partner finishes a
    course. Skips the legacy 'request → admin approves → admin uploads PDF'
    flow entirely. Idempotent: returns if a cert already exists."""
    from app.services.certificate_service import generate_certificate_pdf
    from app.services import tier_service
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
            await tier_service.review_company(db, partner.company_id)
        except Exception:
            pass


async def update_module_progress(
    db: AsyncSession, enrollment_id: int, module_id: str, current_user: User
) -> EnrollmentResponse:
    enrollment = await _own_enrollment(db, enrollment_id, current_user)
    course = _ensure_course_open(enrollment.course)

    module_id = str(module_id)
    if module_id in _module_ids(course, quiz=True):
        raise BadRequestException(
            code="QUIZ_MODULE",
            message="A quiz is completed by passing it, not by marking it done",
        )
    if module_id not in _module_ids(course, quiz=False):
        raise BadRequestException(code="MODULE_NOT_FOUND", message="No such lesson in this course")

    # A fresh dict, not the loaded one mutated in place: the column is plain
    # JSON (not MutableDict), so SQLAlchemy only notices a change when the
    # attribute is assigned a *different* object. Mutating and reassigning the
    # same dict was why only the first module ever persisted.
    progress = _progress_of(enrollment)
    progress[module_id] = True
    enrollment.progress_json = progress

    just_completed = False
    if enrollment.status != EnrollmentStatus.COMPLETED:
        if _completion_requirements_met(course, enrollment):
            _complete(enrollment)
            just_completed = True
        else:
            enrollment.status = EnrollmentStatus.IN_PROGRESS

    await db.flush()

    if just_completed:
        await _auto_issue_certificate(db, enrollment)

    return _enrollment_response(enrollment, current_user.full_name)


async def submit_assessment(
    db: AsyncSession, enrollment_id: int, answers: dict, current_user: User
) -> dict:
    enrollment = await _own_enrollment(db, enrollment_id, current_user)
    course = _ensure_course_open(enrollment.course)

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
    passing_score = course.passing_score or 70

    # Keep the best attempt. A retake — especially after completing — is
    # practice, and must not drag the recorded score below the pass mark the
    # completion (and certificate) was granted on.
    if enrollment.score is None or score > enrollment.score:
        enrollment.score = score
    enrollment.attempt_count = (enrollment.attempt_count or 0) + 1

    if score >= passing_score:
        # Tick the quiz placeholder(s) off so lesson progress reads as done;
        # this is the only way a quiz module enters the progress map.
        quiz_ids = _module_ids(course, quiz=True)
        if quiz_ids:
            progress = _progress_of(enrollment)
            progress.update({qid: True for qid in quiz_ids})
            enrollment.progress_json = progress

    just_completed = False
    if enrollment.status != EnrollmentStatus.COMPLETED:
        if _completion_requirements_met(course, enrollment):
            _complete(enrollment)
            just_completed = True
        else:
            enrollment.status = EnrollmentStatus.IN_PROGRESS

    await db.flush()

    if just_completed:
        await _auto_issue_certificate(db, enrollment)

    return {
        "score": score,
        "passed": score >= passing_score,
        "passing_score": passing_score,
        "attempt_count": enrollment.attempt_count,
        "course_completed": enrollment.status == EnrollmentStatus.COMPLETED,
        "best_score": enrollment.score,
    }


async def get_my_enrollments(
    db: AsyncSession, user_id: int
) -> list[EnrollmentResponse]:
    # Deleted courses drop out of "my courses" the same way they drop out of
    # the catalogue; the enrolment rows themselves are kept for history.
    result = await db.execute(
        select(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .options(joinedload(Enrollment.course))
        .where(Enrollment.user_id == user_id, Course.deleted_at.is_(None))
        .order_by(Enrollment.enrolled_at.desc())
    )
    enrollments = result.unique().scalars().all()

    return [_enrollment_response(e) for e in enrollments]
