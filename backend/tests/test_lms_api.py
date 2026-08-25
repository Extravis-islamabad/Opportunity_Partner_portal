"""The training catalogue and enrolment, over HTTP.

This file exists because the whole course and enrolment API was once deleted by
a commit meant to remove only the certificate-approval queue, and nothing
noticed: the service layer was untouched, every other test still passed, and
the only symptom was the LMS page 404ing in a browser. Tier depends on LMS
completion, so partners silently stopped being able to earn promotion.

So the assertions here are deliberately about the *endpoints existing and being
wired to the right service function with the right guard* — a route table
regression is what this is for, as much as any logic.
"""
import pytest

from app.models.course import CourseStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_course,
    make_user,
    requires_db,
    unique,
)

pytestmark = requires_db
asyncio_test = pytest.mark.asyncio


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.admin = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.admin.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.other_partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.rep = await make_user(db, role=UserRole.SALES_REP)

    # One published course anybody can see, one draft only admins should.
    w.published = await make_course(db, created_by=w.admin.id, title=unique("Published"))
    w.published.status = CourseStatus.PUBLISHED
    w.draft = await make_course(db, created_by=w.admin.id, title=unique("Draft"))
    w.draft.status = CourseStatus.DRAFT
    await db.commit()
    return w


def _titles(body):
    return {item["title"] for item in body["items"]}


class TestCatalogue:
    pytestmark = asyncio_test

    async def test_a_partner_sees_the_published_catalogue(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses", params={"page_size": 100}, headers=auth_header(w.partner)
        )
        assert r.status_code == 200, r.text[:300]
        titles = _titles(r.json())
        assert w.published.title in titles

    async def test_a_partner_does_not_see_drafts(self, client, db):
        # A half-written course is not a course anybody should enrol in.
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses", params={"page_size": 100}, headers=auth_header(w.partner)
        )
        assert w.draft.title not in _titles(r.json())

    async def test_an_admin_sees_drafts_too(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses", params={"page_size": 100}, headers=auth_header(w.admin)
        )
        assert w.draft.title in _titles(r.json())

    async def test_the_listing_is_paginated(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses", params={"page": 1, "page_size": 1}, headers=auth_header(w.partner)
        )
        body = r.json()
        assert len(body["items"]) <= 1
        assert body["page"] == 1 and body["page_size"] == 1
        assert body["total_pages"] >= 1

    async def test_search_narrows_the_catalogue(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/lms/courses",
            params={"search": w.published.title, "page_size": 100},
            headers=auth_header(w.partner),
        )
        assert _titles(r.json()) == {w.published.title}

    async def test_a_course_can_be_opened(self, client, db):
        w = await build(db)
        r = await client.get(
            f"/api/v1/lms/courses/{w.published.id}", headers=auth_header(w.partner)
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["title"] == w.published.title

    async def test_an_unknown_course_is_a_404(self, client, db):
        w = await build(db)
        r = await client.get("/api/v1/lms/courses/99999999", headers=auth_header(w.partner))
        assert r.status_code == 404

    async def test_the_catalogue_needs_a_login(self, client, db):
        await build(db)
        assert (await client.get("/api/v1/lms/courses")).status_code == 401


class TestAuthoring:
    pytestmark = asyncio_test

    async def test_an_admin_can_create_a_course(self, client, db):
        w = await build(db)
        title = unique("New course")
        r = await client.post(
            "/api/v1/lms/courses",
            headers=auth_header(w.admin),
            json={"title": title, "description": "d", "passing_score": 70},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["title"] == title

    async def test_a_partner_cannot_create_a_course(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/lms/courses",
            headers=auth_header(w.partner),
            json={"title": unique("Nope"), "description": "d"},
        )
        assert r.status_code == 403

    async def test_an_admin_can_publish_a_draft(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.draft.id}",
            headers=auth_header(w.admin),
            json={"status": "published"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "published"

    async def test_a_partner_cannot_edit_a_course(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/lms/courses/{w.published.id}",
            headers=auth_header(w.partner),
            json={"title": "hijacked"},
        )
        assert r.status_code == 403

    async def test_an_admin_can_delete_a_course(self, client, db):
        w = await build(db)
        doomed = await make_course(db, created_by=w.admin.id)
        await db.commit()
        r = await client.delete(
            f"/api/v1/lms/courses/{doomed.id}", headers=auth_header(w.admin)
        )
        assert r.status_code == 200, r.text[:300]
        gone = await client.get(
            f"/api/v1/lms/courses/{doomed.id}", headers=auth_header(w.partner)
        )
        assert gone.status_code == 404

    async def test_a_partner_cannot_delete_a_course(self, client, db):
        w = await build(db)
        r = await client.delete(
            f"/api/v1/lms/courses/{w.published.id}", headers=auth_header(w.partner)
        )
        assert r.status_code == 403


class TestEnrolment:
    pytestmark = asyncio_test

    async def test_a_partner_can_enrol(self, client, db):
        w = await build(db)
        r = await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["course_id"] == w.published.id
        assert r.json()["status"] == "enrolled"

    async def test_enrolling_twice_is_refused(self, client, db):
        w = await build(db)
        await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        await db.commit()
        again = await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        assert again.status_code == 409
        assert again.json()["code"] == "ALREADY_ENROLLED"

    async def test_you_cannot_enrol_in_a_draft(self, client, db):
        # Enrolling in something unpublished would count towards tier on a
        # course nobody has finished writing.
        w = await build(db)
        r = await client.post(
            f"/api/v1/lms/courses/{w.draft.id}/enroll", headers=auth_header(w.partner)
        )
        assert r.status_code == 404

    async def test_an_admin_does_not_enrol(self, client, db):
        w = await build(db)
        r = await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.admin)
        )
        assert r.status_code == 403

    async def test_my_enrolments_lists_my_own(self, client, db):
        w = await build(db)
        await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        await db.commit()

        mine = await client.get("/api/v1/lms/enrollments/me", headers=auth_header(w.partner))
        assert mine.status_code == 200, mine.text[:300]
        assert {e["course_id"] for e in mine.json()} == {w.published.id}

    async def test_my_enrolments_shows_nobody_else_s(self, client, db):
        w = await build(db)
        await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        await db.commit()

        theirs = await client.get(
            "/api/v1/lms/enrollments/me", headers=auth_header(w.other_partner)
        )
        assert theirs.json() == []

    async def test_finishing_a_course_records_completion(self, client, db):
        w = await build(db)
        enrolled = await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        await db.commit()
        enrollment_id = enrolled.json()["id"]

        r = await client.put(
            f"/api/v1/lms/enrollments/{enrollment_id}",
            headers=auth_header(w.partner),
            json={"status": "completed"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "completed"
        assert r.json()["completed_at"] is not None

    async def test_you_cannot_advance_somebody_else_s_enrolment(self, client, db):
        # Completion feeds the company's tier, which sets the commission rate.
        w = await build(db)
        enrolled = await client.post(
            f"/api/v1/lms/courses/{w.published.id}/enroll", headers=auth_header(w.partner)
        )
        await db.commit()

        r = await client.put(
            f"/api/v1/lms/enrollments/{enrolled.json()['id']}",
            headers=auth_header(w.other_partner),
            json={"status": "completed"},
        )
        assert r.status_code == 404
