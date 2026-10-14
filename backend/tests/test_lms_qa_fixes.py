"""Regressions from the LMS API QA pass.

Each class is one reported bug. The common thread is that course completion
feeds a company's tier (and so its commission rate) and mints a certificate,
so every way of reaching "completed" has to require the same real work — and
the admin side has to be able to author the quiz that work is measured by.
"""
import pytest

from app.models.course import CourseStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_course,
    make_enrollment,
    make_user,
    requires_db,
    unique,
)

pytestmark = requires_db
asyncio_test = pytest.mark.asyncio


QUIZ = [
    {"id": 1, "question": "2 + 2?", "options": ["3", "4"], "correct_answer": 1, "points": 1},
    {"id": 2, "question": "Sky colour?", "options": ["Blue", "Green", "Red"], "correct_answer": 0, "points": 1},
]
ALL_RIGHT = {"1": 1, "2": 0}
HALF_RIGHT = {"1": 1, "2": 2}

MODULES = [
    {"id": "m1", "title": "Intro", "type": "text", "order": 0},
    {"id": "m2", "title": "Deep dive", "type": "video", "content_url": "https://example.com/v.mp4", "order": 1},
    {"id": "m3", "title": "Check", "type": "quiz", "order": 2},
]


class World:
    pass


async def build(db, *, modules=None, assessment=None, status=CourseStatus.PUBLISHED):
    w = World()
    w.admin = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.admin.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.course = await make_course(db, created_by=w.admin.id, title=unique("QA course"))
    w.course.status = status
    w.course.modules_json = MODULES if modules is None else modules
    w.course.assessment_json = assessment or []
    w.course.passing_score = 70
    await db.commit()
    return w


async def enrol(client, db, w):
    r = await client.post(
        f"/api/v1/lms/courses/{w.course.id}/enroll", headers=auth_header(w.partner)
    )
    assert r.status_code == 201, r.text[:300]
    return r.json()["id"]


async def mark(client, w, enrollment_id, module_id):
    return await client.put(
        f"/api/v1/lms/enrollments/{enrollment_id}/progress",
        headers=auth_header(w.partner),
        json={"module_id": module_id},
    )


async def my_enrollment(client, w):
    r = await client.get("/api/v1/lms/enrollments/me", headers=auth_header(w.partner))
    assert r.status_code == 200, r.text[:300]
    return next((e for e in r.json() if e["course_id"] == w.course.id), None)


class TestAdminCanEditDrafts:
    pytestmark = asyncio_test

    async def test_an_admin_can_edit_a_draft(self, client, db):
        w = await build(db, status=CourseStatus.DRAFT)
        r = await client.put(
            f"/api/v1/lms/courses/{w.course.id}",
            headers=auth_header(w.admin),
            json={"title": "Renamed draft"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["title"] == "Renamed draft"
        assert r.json()["status"] == "draft"

    async def test_an_admin_can_unpublish(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.course.id}",
            headers=auth_header(w.admin),
            json={"status": "draft"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "draft"


class TestModuleProgress:
    pytestmark = asyncio_test

    async def test_every_module_persists_not_just_the_first(self, client, db):
        w = await build(db, modules=MODULES[:2])
        eid = await enrol(client, db, w)

        assert (await mark(client, w, eid, "m1")).status_code == 200
        r = await mark(client, w, eid, "m2")
        assert r.status_code == 200, r.text[:300]

        e = await my_enrollment(client, w)
        assert e["progress_json"] == {"m1": True, "m2": True}
        assert e["status"] == "completed"

    async def test_an_unknown_module_is_refused(self, client, db):
        w = await build(db)
        eid = await enrol(client, db, w)
        r = await mark(client, w, eid, "no-such-module")
        assert r.status_code == 400
        assert r.json()["code"] == "MODULE_NOT_FOUND"

    async def test_the_quiz_module_cannot_be_ticked_off(self, client, db):
        w = await build(db, assessment=QUIZ)
        eid = await enrol(client, db, w)
        r = await mark(client, w, eid, "m3")
        assert r.status_code == 400
        assert r.json()["code"] == "QUIZ_MODULE"

    async def test_lessons_alone_do_not_finish_a_course_with_a_quiz(self, client, db):
        w = await build(db, assessment=QUIZ)
        eid = await enrol(client, db, w)
        await mark(client, w, eid, "m1")
        r = await mark(client, w, eid, "m2")
        assert r.json()["status"] == "in_progress"

    async def test_a_legacy_non_dict_progress_value_does_not_500(self, client, db):
        # PUT /enrollments used to store whatever it was given.
        w = await build(db, modules=MODULES[:2])
        enrollment = await make_enrollment(db, user_id=w.partner.id, course_id=w.course.id)
        enrollment.progress_json = "garbage"
        await db.commit()

        r = await mark(client, w, enrollment.id, "m1")
        assert r.status_code == 200, r.text[:300]
        assert r.json()["progress_json"] == {"m1": True}


class TestNoSelfCompletion:
    pytestmark = asyncio_test

    async def test_a_partner_cannot_declare_an_unfinished_course_complete(self, client, db):
        w = await build(db, assessment=QUIZ)
        eid = await enrol(client, db, w)
        r = await client.put(
            f"/api/v1/lms/enrollments/{eid}",
            headers=auth_header(w.partner),
            json={"status": "completed"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "COMPLETION_REQUIREMENTS_NOT_MET"
        assert (await my_enrollment(client, w))["status"] == "enrolled"

    async def test_a_partner_cannot_write_progress_directly(self, client, db):
        w = await build(db)
        eid = await enrol(client, db, w)
        r = await client.put(
            f"/api/v1/lms/enrollments/{eid}",
            headers=auth_header(w.partner),
            json={"status": "completed", "progress_json": {"m1": True, "m2": True, "m3": True}},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "PROGRESS_READ_ONLY"
        e = await my_enrollment(client, w)
        assert e["status"] == "enrolled"
        assert not e["progress_json"]

    async def test_a_malformed_progress_value_is_a_422(self, client, db):
        w = await build(db)
        eid = await enrol(client, db, w)
        r = await client.put(
            f"/api/v1/lms/enrollments/{eid}",
            headers=auth_header(w.partner),
            json={"progress_json": "not a map"},
        )
        assert r.status_code == 422

    async def test_a_completed_enrolment_cannot_be_moved_back(self, client, db):
        w = await build(db, modules=MODULES[:1])
        eid = await enrol(client, db, w)
        await mark(client, w, eid, "m1")
        r = await client.put(
            f"/api/v1/lms/enrollments/{eid}",
            headers=auth_header(w.partner),
            json={"status": "enrolled"},
        )
        assert r.status_code == 400
        assert (await my_enrollment(client, w))["status"] == "completed"


class TestQuizAuthoring:
    pytestmark = asyncio_test

    async def test_an_admin_can_create_a_course_with_a_quiz(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/lms/courses",
            headers=auth_header(w.admin),
            json={"title": unique("Quiz course"), "assessment_json": QUIZ, "passing_score": 80},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["assessment_json"] == QUIZ
        assert r.json()["passing_score"] == 80

    async def test_an_admin_can_edit_the_quiz(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.course.id}",
            headers=auth_header(w.admin),
            json={"assessment_json": QUIZ[:1], "passing_score": 50},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["assessment_json"] == QUIZ[:1]
        assert r.json()["passing_score"] == 50

    @pytest.mark.parametrize("question", [
        {"id": 1, "question": "q", "options": ["a", "b"], "correct_answer": 2},
        {"id": 1, "question": "q", "options": ["a"], "correct_answer": 0},
        {"id": 1, "question": "", "options": ["a", "b"], "correct_answer": 0},
        {"id": 1, "question": "q", "options": ["a", "b"]},
        {"id": 1, "question": "q", "options": ["a", "b"], "correct_answer": "a"},
    ])
    async def test_a_malformed_question_is_refused(self, client, db, question):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.course.id}",
            headers=auth_header(w.admin),
            json={"assessment_json": [question]},
        )
        assert r.status_code == 422, r.text[:300]

    async def test_a_partner_sees_the_questions_but_not_the_answers(self, client, db):
        w = await build(db, assessment=QUIZ)
        r = await client.get(
            f"/api/v1/lms/courses/{w.course.id}", headers=auth_header(w.partner)
        )
        assert r.status_code == 200
        quiz = r.json()["assessment_json"]
        assert [q["question"] for q in quiz] == [q["question"] for q in QUIZ]
        assert all("correct_answer" not in q for q in quiz)

        listing = await client.get(
            "/api/v1/lms/courses",
            params={"search": w.course.title},
            headers=auth_header(w.partner),
        )
        assert all(
            "correct_answer" not in q
            for c in listing.json()["items"] for q in c["assessment_json"]
        )

    async def test_an_admin_sees_the_answer_key(self, client, db):
        w = await build(db, assessment=QUIZ)
        r = await client.get(
            f"/api/v1/lms/courses/{w.course.id}", headers=auth_header(w.admin)
        )
        assert r.json()["assessment_json"] == QUIZ


class TestQuizCompletion:
    pytestmark = asyncio_test

    async def _submit(self, client, w, eid, answers):
        r = await client.post(
            f"/api/v1/lms/enrollments/{eid}/submit-assessment",
            headers=auth_header(w.partner),
            json={"answers": answers},
        )
        assert r.status_code == 200, r.text[:300]
        return r.json()

    async def test_lessons_plus_a_passed_quiz_completes(self, client, db):
        w = await build(db, assessment=QUIZ)
        eid = await enrol(client, db, w)

        result = await self._submit(client, w, eid, ALL_RIGHT)
        assert result["passed"] and not result["course_completed"]

        await mark(client, w, eid, "m1")
        r = await mark(client, w, eid, "m2")
        assert r.json()["status"] == "completed"
        assert r.json()["progress_json"] == {"m1": True, "m2": True, "m3": True}

    async def test_a_worse_retake_keeps_the_best_score_and_completion(self, client, db):
        w = await build(db, modules=[], assessment=QUIZ)
        eid = await enrol(client, db, w)

        first = await self._submit(client, w, eid, ALL_RIGHT)
        assert first["course_completed"] and first["score"] == 100

        retake = await self._submit(client, w, eid, HALF_RIGHT)
        assert retake["score"] == 50 and not retake["passed"]
        assert retake["best_score"] == 100 and retake["course_completed"]

        e = await my_enrollment(client, w)
        assert e["status"] == "completed"
        assert e["score"] == 100
        assert e["attempt_count"] == 2


class TestInputValidation:
    pytestmark = asyncio_test

    async def test_an_unknown_status_filter_is_a_422(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses", params={"status": "bogus"}, headers=auth_header(w.admin)
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("field", ["title", "status", "passing_score", "modules_json", "assessment_json"])
    async def test_nulling_a_required_field_is_a_422(self, client, db, field):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.course.id}",
            headers=auth_header(w.admin),
            json={field: None},
        )
        assert r.status_code == 422, r.text[:300]


class TestWithdrawnCourses:
    pytestmark = asyncio_test

    async def test_no_progress_on_an_unpublished_course(self, client, db):
        w = await build(db)
        eid = await enrol(client, db, w)
        w.course.status = CourseStatus.DRAFT
        await db.commit()

        r = await mark(client, w, eid, "m1")
        assert r.status_code == 400
        assert r.json()["code"] == "COURSE_UNAVAILABLE"

    async def test_no_progress_on_a_deleted_course(self, client, db):
        w = await build(db)
        eid = await enrol(client, db, w)
        await client.delete(f"/api/v1/lms/courses/{w.course.id}", headers=auth_header(w.admin))

        r = await mark(client, w, eid, "m1")
        assert r.status_code == 400
        assert r.json()["code"] == "COURSE_UNAVAILABLE"

    async def test_a_deleted_course_drops_out_of_my_enrolments(self, client, db):
        w = await build(db)
        await enrol(client, db, w)
        await client.delete(f"/api/v1/lms/courses/{w.course.id}", headers=auth_header(w.admin))

        assert await my_enrollment(client, w) is None
