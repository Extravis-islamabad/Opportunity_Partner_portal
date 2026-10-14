"""The partner-portal feedback round.

Covers the behaviour that changed in migration 033, at the API:

- a company can have several channel managers, and each of them gets the
  company in scope — reading it, acting on its opportunities, and being told
  about it;
- every admin can read every opportunity, but only a channel manager of its
  company acts on it;
- a distributor's users are reported with their company's type, so the UI
  can call them distributors;
- activity reminders fire once, when due, as a notification to the rep;
- handing over a leaver's work moves their co-managed companies too.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.company import CompanyType, company_channel_managers
from app.models.notification import Notification
from app.models.opportunity import OpportunityStatus
from app.models.sales_activity import ActivityType, SalesActivity
from app.models.user import UserRole

from .conftest import (
    auth_header, make_company, make_opportunity, make_user, requires_db, unique,
)

pytestmark = [pytest.mark.asyncio, requires_db]


async def _co_managed_world(db):
    """Company X, primary manager A, co-manager B; outsider C manages nothing."""
    superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    a = await make_user(db, role=UserRole.ADMIN)
    b = await make_user(db, role=UserRole.ADMIN)
    c = await make_user(db, role=UserRole.ADMIN)
    company = await make_company(db, channel_manager_id=a.id)
    await db.execute(
        company_channel_managers.insert(),
        [{"company_id": company.id, "user_id": a.id}, {"company_id": company.id, "user_id": b.id}],
    )
    partner = await make_user(db, role=UserRole.PARTNER, company_id=company.id)
    await db.commit()
    return superadmin, a, b, c, company, partner


class TestSeveralChannelManagers:
    async def test_superadmin_sets_several_managers(self, client, db):
        superadmin, a, b, c, company, _ = await _co_managed_world(db)
        r = await client.put(
            f"/api/v1/companies/{company.id}",
            headers=auth_header(superadmin),
            json={"channel_manager_ids": [c.id, a.id]},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["channel_manager_id"] == c.id
        assert {m["id"] for m in r.json()["channel_managers"]} == {a.id, c.id}

        # B was replaced: out of scope now. C was added: in scope.
        assert (await client.get(f"/api/v1/companies/{company.id}", headers=auth_header(b))).status_code == 403
        assert (await client.get(f"/api/v1/companies/{company.id}", headers=auth_header(c))).status_code == 200

    async def test_channel_manager_cannot_change_the_managers(self, client, db):
        _, a, _, c, company, _ = await _co_managed_world(db)
        r = await client.put(
            f"/api/v1/companies/{company.id}",
            headers=auth_header(a),
            json={"channel_manager_ids": [a.id, c.id]},
        )
        assert r.status_code == 403

    async def test_channel_manager_can_save_other_fields(self, client, db):
        # The edit form used to always send channel_manager_id, so a channel
        # manager could not save any edit at all. Without it, they can — and
        # clearing the optional city is allowed.
        _, a, _, _, company, _ = await _co_managed_world(db)
        r = await client.put(
            f"/api/v1/companies/{company.id}",
            headers=auth_header(a),
            json={"industry": "Banking", "city": ""},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["industry"] == "Banking"
        assert r.json()["city"] is None

    async def test_co_manager_reads_and_acts(self, client, db):
        _, _, b, _, company, partner = await _co_managed_world(db)
        opp = await make_opportunity(
            db, company_id=company.id, submitted_by=partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        listed = await client.get("/api/v1/companies?page_size=100", headers=auth_header(b))
        assert company.id in {c["id"] for c in listed.json()["items"]}

        detail = await client.get(f"/api/v1/opportunities/{opp.id}", headers=auth_header(b))
        assert detail.status_code == 200
        assert detail.json()["viewer_can_review"] is True
        # Opening it claimed it, because B may review it.
        assert detail.json()["status"] == "under_review"

        approved = await client.post(
            f"/api/v1/opportunities/{opp.id}/approve", headers=auth_header(b), json={}
        )
        assert approved.status_code == 200, approved.text[:300]

    async def test_outsider_reads_but_cannot_act(self, client, db):
        _, _, _, c, company, partner = await _co_managed_world(db)
        opp = await make_opportunity(
            db, company_id=company.id, submitted_by=partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        detail = await client.get(f"/api/v1/opportunities/{opp.id}", headers=auth_header(c))
        assert detail.status_code == 200
        assert detail.json()["viewer_can_review"] is False
        assert detail.json()["status"] == "pending_review"  # not claimed

        # The POC panel on that page loads for them too, read-only.
        poc = await client.get(f"/api/v1/pocs/by-opportunity/{opp.id}", headers=auth_header(c))
        assert poc.status_code == 200

        approved = await client.post(
            f"/api/v1/opportunities/{opp.id}/approve", headers=auth_header(c), json={}
        )
        assert approved.status_code == 403

    async def test_handover_moves_co_managed_companies(self, client, db):
        superadmin, _, b, c, company, _ = await _co_managed_world(db)
        r = await client.post(
            f"/api/v1/users/{b.id}/handover",
            headers=auth_header(superadmin),
            json={"to_user_id": c.id},
        )
        assert r.status_code in (200, 201), r.text[:300]
        rows = (await db.execute(
            select(company_channel_managers.c.user_id).where(
                company_channel_managers.c.company_id == company.id
            )
        )).scalars().all()
        assert b.id not in rows and c.id in rows


class TestCompanyCreation:
    async def test_admin_adds_a_reseller_under_a_distributor_they_manage(self, client, db, monkeypatch):
        async def _no_mail(**kwargs):
            return True
        monkeypatch.setattr("app.services.partner_service.send_template_email", _no_mail)

        manager = await make_user(db, role=UserRole.ADMIN)
        outsider = await make_user(db, role=UserRole.ADMIN)
        distributor = await make_company(
            db, channel_manager_id=manager.id, company_type=CompanyType.DISTRIBUTOR,
        )
        await db.commit()

        body = {
            "name": unique("Reseller"), "country": "PK", "industry": "IT",
            "contact_email": f"{unique('contact').lower()}@fixture.example.com",
            "contact_name": "Reseller Contact",
            "channel_manager_ids": [manager.id],
            "company_type": "partner", "parent_distributor_id": distributor.id,
        }
        denied = await client.post("/api/v1/companies", headers=auth_header(outsider), json=body)
        assert denied.status_code == 403

        r = await client.post("/api/v1/companies", headers=auth_header(manager), json=body)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["parent_distributor_id"] == distributor.id
        # The reseller's contact got a portal account of its own company.
        assert r.json()["contact_invite"] == "sent"
        users = await client.get(
            f"/api/v1/users?company_id={r.json()['id']}", headers=auth_header(manager)
        )
        assert [u["email"] for u in users.json()["items"]] == [body["contact_email"]]
        assert users.json()["items"][0]["company_type"] == "partner"

    async def test_distributor_users_report_their_company_type(self, client, db):
        superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        distributor = await make_company(
            db, channel_manager_id=superadmin.id, company_type=CompanyType.DISTRIBUTOR,
        )
        staff = await make_user(db, role=UserRole.PARTNER, company_id=distributor.id)
        await db.commit()
        r = await client.get(f"/api/v1/users?company_id={distributor.id}", headers=auth_header(superadmin))
        row = next(u for u in r.json()["items"] if u["id"] == staff.id)
        assert row["role"] == "partner"
        assert row["company_type"] == "distributor"


class TestOptionalCompanyLocation:
    async def test_dashboard_analytics_survive_a_company_without_region(self, client, db):
        # Region became optional; the analytics region breakdown required a
        # string and answered 400 for the whole dashboard once one was blank.
        superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(db, channel_manager_id=superadmin.id)
        company.region = None
        company.city = None
        await db.commit()

        r = await client.get("/api/v1/dashboard/admin/analytics", headers=auth_header(superadmin))
        assert r.status_code == 200, r.text[:300]
        assert "Unspecified" in {row["region"] for row in r.json()["regions"]}

        export = await client.get("/api/v1/exports/companies.xlsx", headers=auth_header(superadmin))
        assert export.status_code == 200


class TestActivityReminders:
    async def test_weekend_deployment_with_partner_and_reminder(self, client, db):
        rep = await make_user(db, role=UserRole.SALES_REP)
        await db.commit()
        saturday = date.today() - timedelta(days=1)
        while saturday.weekday() != 5:
            saturday -= timedelta(days=1)
        at = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(microsecond=0)
        r = await client.post(
            "/api/v1/activities",
            headers=auth_header(rep),
            json={
                "activity_date": saturday.isoformat(), "activity_type": "deployment",
                "customer_name": "HUGO BANK / Ali", "partner_name": "NetSoft",
                "reminder_at": at.isoformat(), "reminder_note": "Send the revised quote",
            },
        )
        assert r.status_code == 201, r.text[:300]
        body = r.json()
        assert body["activity_type_label"] == "Deployment"
        assert body["partner_name"] == "NetSoft"
        assert body["reminder_sent_at"] is None

        upcoming = await client.get("/api/v1/activities/reminders", headers=auth_header(rep))
        assert [a["id"] for a in upcoming.json()] == [body["id"]]

    async def test_past_reminder_refused(self, client, db):
        rep = await make_user(db, role=UserRole.SALES_REP)
        await db.commit()
        r = await client.post(
            "/api/v1/activities",
            headers=auth_header(rep),
            json={
                "activity_date": date.today().isoformat(), "activity_type": "call",
                "reminder_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            },
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_REMINDER"

    async def test_due_reminder_notifies_once(self, db, monkeypatch):
        from app.services import sales_activity_service

        async def _no_mail(**kwargs):
            return True
        monkeypatch.setattr("app.services.notification_service.send_template_email", _no_mail)

        rep = await make_user(db, role=UserRole.SALES_REP)
        due = SalesActivity(
            user_id=rep.id, activity_date=date.today(), activity_type=ActivityType.FOLLOW_UP,
            customer_name="Pak Qatar", reminder_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            reminder_note="Call back about the PO",
        )
        later = SalesActivity(
            user_id=rep.id, activity_date=date.today(), activity_type=ActivityType.CALL,
            reminder_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add_all([due, later])
        await db.commit()

        # Assert on this rep's rows only: the test database outlives a run, so
        # reminders other tests set "in a few hours" come due in later runs
        # and are swept here too.
        await sales_activity_service.send_due_reminders(db)
        await db.commit()
        await db.refresh(due)
        first_sent_at = due.reminder_sent_at
        assert first_sent_at is not None
        await sales_activity_service.send_due_reminders(db)
        await db.commit()
        await db.refresh(due)
        assert due.reminder_sent_at == first_sent_at  # not fired twice

        notes = (await db.execute(
            select(Notification).where(
                Notification.user_id == rep.id, Notification.type == "activity_reminder"
            )
        )).scalars().all()
        assert len(notes) == 1
        assert "Pak Qatar" in notes[0].title
        assert notes[0].message == "Call back about the PO"
        await db.refresh(later)
        assert later.reminder_sent_at is None
