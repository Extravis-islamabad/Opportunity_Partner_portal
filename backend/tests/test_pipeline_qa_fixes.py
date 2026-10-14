"""Regression tests for the pipeline bugs found in the QA pass.

Each class pins one reported defect: the request that used to 500, leak or
slip through, and what it must do instead.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.company import CompanyType
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.poc_team import PocTeamRole
from app.models.sales_activity import ActivityType, SalesActivity
from app.models.user import UserRole

from .conftest import (
    auth_header, make_company, make_license, make_opportunity, make_poc,
    make_team_member, make_user, requires_db, unique,
)

pytestmark = [pytest.mark.asyncio, requires_db]


async def _world(db):
    admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    company = await make_company(db, channel_manager_id=admin.id)
    partner = await make_user(db, role=UserRole.PARTNER, company_id=company.id)
    rep = await make_user(db, role=UserRole.SALES_REP)
    await db.commit()
    return admin, company, partner, rep


def _opp_body(**extra):
    body = {
        "name": unique("QA opp"), "customer_name": unique("QA cust"),
        "region": "NA", "country": "US", "city": "Austin", "worth": 1000,
        "closing_date": "2027-01-01", "requirements": "r",
    }
    body.update(extra)
    return body


class TestOpportunityEditing:
    async def test_partner_edits_and_resubmits_a_rejected_opportunity(self, client, db):
        # Reading opp.reviewer on a rejected deal used to lazy-load and 500,
        # so a rejected deal could never be fixed and sent back.
        admin, company, partner, _ = await _world(db)
        opp = await make_opportunity(db, company_id=company.id, submitted_by=partner.id,
                                     status=OpportunityStatus.REJECTED)
        opp.reviewed_by = admin.id
        await db.commit()
        r = await client.put(f"/api/v1/opportunities/{opp.id}", headers=auth_header(partner),
                             json={"requirements": "now with detail"})
        assert r.status_code == 200, r.text[:300]
        r = await client.post(f"/api/v1/opportunities/{opp.id}/submit", headers=auth_header(partner))
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "pending_review"

    async def test_sales_rep_assignment_is_validated(self, client, db):
        admin, company, partner, rep = await _world(db)
        bad = await client.post("/api/v1/opportunities", headers=auth_header(partner),
                                json=_opp_body(sales_rep_id=admin.id))
        assert bad.status_code == 400
        missing = await client.post("/api/v1/opportunities", headers=auth_header(partner),
                                    json=_opp_body(sales_rep_id=999999))
        assert missing.status_code == 400
        ok = await client.post("/api/v1/opportunities", headers=auth_header(partner),
                               json=_opp_body(sales_rep_id=rep.id))
        assert ok.status_code == 201, ok.text[:300]
        assert ok.json()["sales_rep_name"] == rep.full_name

    async def test_explicit_null_on_required_field_is_a_400(self, client, db):
        _, company, partner, _ = await _world(db)
        opp = await make_opportunity(db, company_id=company.id, submitted_by=partner.id,
                                     status=OpportunityStatus.DRAFT)
        await db.commit()
        for field in ("name", "worth", "closing_date", "currency"):
            r = await client.put(f"/api/v1/opportunities/{opp.id}", headers=auth_header(partner),
                                 json={field: None})
            assert r.status_code == 400, (field, r.status_code)

    async def test_bad_filters_and_oversized_numbers_are_4xx(self, client, db):
        _, _, partner, _ = await _world(db)
        r = await client.get("/api/v1/opportunities?status=bogus", headers=auth_header(partner))
        assert r.status_code == 422
        r = await client.post("/api/v1/opportunities", headers=auth_header(partner),
                              json=_opp_body(products=[{"product": "MonetX", "device_count": 10**12}]))
        assert r.status_code == 422

    async def test_search_wildcards_are_literal(self, client, db):
        _, company, partner, _ = await _world(db)
        await make_opportunity(db, company_id=company.id, submitted_by=partner.id)
        await db.commit()
        r = await client.get("/api/v1/opportunities?search=%25", headers=auth_header(partner))
        assert r.status_code == 200
        assert r.json()["total"] == 0


class TestReviewClock:
    async def test_manual_claim_starts_the_clock(self, client, db):
        admin, company, partner, _ = await _world(db)
        opp = await make_opportunity(db, company_id=company.id, submitted_by=partner.id)
        await db.commit()
        r = await client.post(f"/api/v1/opportunities/{opp.id}/review", headers=auth_header(admin))
        assert r.status_code == 200
        assert r.json()["viewer_can_review"] is True
        await db.refresh(opp)
        assert opp.review_claimed_at is not None


class TestPocRules:
    async def test_no_poc_on_a_draft_and_no_po_before_approval(self, client, db):
        admin, company, partner, _ = await _world(db)
        draft = await make_opportunity(db, company_id=company.id, submitted_by=partner.id,
                                       status=OpportunityStatus.DRAFT)
        pending = await make_opportunity(db, company_id=company.id, submitted_by=partner.id)
        await db.commit()
        r = await client.post(f"/api/v1/pocs/by-opportunity/{draft.id}/start",
                              headers=auth_header(admin), json={"start_date": str(date.today())})
        assert r.status_code == 409
        r = await client.put(f"/api/v1/pocs/licenses/by-opportunity/{pending.id}",
                             headers=auth_header(admin), json={"po_number": "PO-1"})
        assert r.status_code == 409

    async def test_partner_sees_a_redacted_team(self, client, db):
        admin, company, partner, rep = await _world(db)
        opp = await make_opportunity(db, company_id=company.id, submitted_by=partner.id,
                                     status=OpportunityStatus.APPROVED)
        poc = await make_poc(db, opportunity_id=opp.id)
        await make_team_member(db, poc_id=poc.id, user_id=rep.id,
                               role=list(PocTeamRole)[0], assigned_by=admin.id)
        await db.commit()
        r = await client.get(f"/api/v1/pocs/{poc.id}/team?include_removed=true",
                             headers=auth_header(partner))
        assert r.status_code == 200
        member = r.json()[0]
        assert member["user_name"] == rep.full_name
        assert member.get("user_email") is None


class TestDuplicateCheckRedaction:
    async def test_partner_is_not_shown_another_partners_deal(self, client, db):
        admin, company, partner, _ = await _world(db)
        other_co = await make_company(db, channel_manager_id=admin.id)
        other = await make_user(db, role=UserRole.PARTNER, company_id=other_co.id)
        theirs = await make_opportunity(db, company_id=other_co.id, submitted_by=other.id)
        await db.commit()
        r = await client.post("/api/v1/opportunities/check-duplicate", headers=auth_header(partner),
                              json={"customer_name": theirs.customer_name, "country": "US"})
        assert r.status_code == 200
        body = r.json()
        matches = body["exact_matches"] + body["fuzzy_matches"]
        assert matches, body
        for m in matches:
            assert "name" not in m and "worth" not in m and m.get("company_name") is None
        assert other_co.name not in " ".join(body["messages"])

        # An admin still sees the whole picture.
        r = await client.post("/api/v1/opportunities/check-duplicate", headers=auth_header(admin),
                              json={"customer_name": theirs.customer_name, "country": "US"})
        assert r.json()["exact_matches"][0]["company_name"] == other_co.name


class TestRenewalOfDirectDeal:
    async def test_renewing_a_partnerless_licence(self, client, db):
        admin, _, _, rep = await _world(db)
        opp = Opportunity(
            name=unique("Direct"), customer_name=unique("Cust"), region="NA", country="US",
            city="Austin", worth=5000, closing_date=date(2027, 1, 1), requirements="r",
            status=OpportunityStatus.WON, submitted_by=rep.id, sales_rep_id=rep.id, company_id=None,
        )
        db.add(opp)
        await db.flush()
        lic = await make_license(db, opportunity_id=opp.id)
        await db.commit()
        r = await client.post(f"/api/v1/renewals/{lic.id}", headers=auth_header(admin), json={})
        assert r.status_code == 201, r.text[:300]
        renewal = (await db.execute(
            select(Opportunity).where(Opportunity.id == r.json()["id"])
        )).scalar_one()
        assert renewal.company_id is None
        assert r.json()["renewal_of_license_id"] == lic.id


class TestActivityLinks:
    async def test_rep_cannot_link_an_opportunity_they_cannot_see(self, client, db):
        _, company, partner, rep = await _world(db)
        opp = await make_opportunity(db, company_id=company.id, submitted_by=partner.id)
        await db.commit()
        r = await client.post("/api/v1/activities", headers=auth_header(rep), json={
            "activity_date": str(date.today()), "activity_type": "meeting", "opportunity_id": opp.id,
        })
        assert r.status_code == 403

    async def test_editing_after_the_reminder_fired(self, client, db):
        _, _, _, rep = await _world(db)
        fired_at = datetime.now(timezone.utc) - timedelta(hours=1)
        a = SalesActivity(
            user_id=rep.id, activity_date=date.today(), activity_type=ActivityType.CALL,
            reminder_at=fired_at, reminder_sent_at=fired_at, reminder_note="call back",
        )
        db.add(a)
        await db.commit()
        # The edit form always sends the (now past) reminder back unchanged.
        r = await client.put(f"/api/v1/activities/{a.id}", headers=auth_header(rep), json={
            "notes": "fixed a typo", "reminder_at": fired_at.isoformat(),
        })
        assert r.status_code == 200, r.text[:300]
        assert r.json()["reminder_sent_at"] is not None  # not re-armed


class TestCompanyRules:
    async def test_null_name_duplicate_name_and_distributor_with_resellers(self, client, db):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        dist = await make_company(db, channel_manager_id=admin.id, company_type=CompanyType.DISTRIBUTOR)
        child = await make_company(db, channel_manager_id=admin.id)
        child.parent_distributor_id = dist.id
        await db.commit()
        h = auth_header(admin)

        r = await client.put(f"/api/v1/companies/{child.id}", headers=h, json={"name": None})
        assert r.status_code == 400
        r = await client.put(f"/api/v1/companies/{child.id}", headers=h, json={"name": dist.name.upper()})
        assert r.status_code == 409
        r = await client.delete(f"/api/v1/companies/{dist.id}", headers=h)
        assert r.status_code == 409
        # Changing type while unlinking in the same request is allowed.
        r = await client.put(f"/api/v1/companies/{child.id}", headers=h,
                             json={"company_type": "customer", "parent_distributor_id": None})
        assert r.status_code == 200, r.text[:300]
