"""A sales rep locking an opportunity for a partner.

Registration used to be a partner-only route: the partner registered, the
approval locked the customer to them. An Extravis rep working a deal with a
partner had no way to raise it — they had to ask the partner to type it in.

Now a rep can register too, naming the partner the lock is for and the
customer it is on. The assertions here are about the consequences of that
being done on somebody else's behalf: the lock is judged against the partner
chosen, not the rep; the opportunity lands in the rep's own scoped list; the
partner is told; and nobody can use the new field to register for a company
that cannot hold a lock.
"""
from datetime import date, timedelta

import pytest

from app.models.company import CompanyStatus, CompanyType
from app.models.deal_registration import DealStatus
from app.models.opportunity import OpportunityStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_deal,
    make_opportunity,
    make_user,
    requires_db,
    unique,
)

pytestmark = [requires_db, pytest.mark.asyncio]


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.manager = await make_user(db, role=UserRole.ADMIN)
    w.partner_co = await make_company(db, channel_manager_id=w.manager.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.partner_co.id)
    w.other_co = await make_company(db, channel_manager_id=w.manager.id)
    w.other_partner = await make_user(
        db, role=UserRole.PARTNER, company_id=w.other_co.id
    )
    w.customer_co = await make_company(
        db, channel_manager_id=w.manager.id, company_type=CompanyType.CUSTOMER
    )
    w.inactive_co = await make_company(db, channel_manager_id=w.manager.id)
    w.inactive_co.status = CompanyStatus.INACTIVE
    w.rep = await make_user(db, role=UserRole.SALES_REP)
    w.other_rep = await make_user(db, role=UserRole.SALES_REP)
    await db.commit()
    return w


def payload(company_id=None, **overrides):
    body = {
        "name": unique("Opp"),
        "customer_name": unique("Customer"),
        "region": "NA",
        "country": "US",
        "city": "Austin",
        "worth": 25000,
        "closing_date": (date.today() + timedelta(days=90)).isoformat(),
        "requirements": "Rep-raised registration",
    }
    if company_id is not None:
        body["company_id"] = company_id
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Registering
# ---------------------------------------------------------------------------

class TestRepRegisters:
    async def test_a_rep_can_lock_an_opportunity_for_a_partner(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id),
        )
        assert r.status_code == 201, r.text[:300]
        body = r.json()
        # The lock is the partner's; the record of who raised it is the rep's.
        assert body["company_id"] == w.partner_co.id
        assert body["company_name"] == w.partner_co.name
        assert body["submitted_by"] == w.rep.id

    async def test_the_registration_is_assigned_to_the_rep(self, client, db):
        # A rep's list and every per-record check are scoped by sales_rep_id.
        # Without the assignment they could raise an opportunity and then
        # never open it again.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id),
        )
        assert r.json()["sales_rep_id"] == w.rep.id

        listed = await client.get(
            "/api/v1/opportunities?page_size=100", headers=auth_header(w.rep)
        )
        assert r.json()["id"] in {i["id"] for i in listed.json()["items"]}

        detail = await client.get(
            f"/api/v1/opportunities/{r.json()['id']}", headers=auth_header(w.rep)
        )
        assert detail.status_code == 200

    async def test_a_rep_cannot_assign_it_to_somebody_else(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id, sales_rep_id=w.other_rep.id),
        )
        assert r.status_code == 201
        assert r.json()["sales_rep_id"] == w.rep.id

    async def test_the_partner_sees_it_in_their_pipeline(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id),
        )
        listed = await client.get(
            "/api/v1/opportunities?page_size=100", headers=auth_header(w.partner)
        )
        assert r.json()["id"] in {i["id"] for i in listed.json()["items"]}

        # ...and not in anybody else's.
        other = await client.get(
            "/api/v1/opportunities?page_size=100", headers=auth_header(w.other_partner)
        )
        assert r.json()["id"] not in {i["id"] for i in other.json()["items"]}

    async def test_the_partner_is_told(self, client, db):
        # The lock is being taken in their name.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id),
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        mine = [
            n for n in notes.json()["items"]
            if n["type"] == "opportunity_registered_for_you"
            and n.get("entity_id") == r.json()["id"]
        ]
        assert mine, "the partner was not told a rep registered for them"

        other = await client.get(
            "/api/v1/notifications", headers=auth_header(w.other_partner)
        )
        assert not any(
            n["type"] == "opportunity_registered_for_you"
            and n.get("entity_id") == r.json()["id"]
            for n in other.json()["items"]
        )

    async def test_submitting_straight_away_reaches_the_admins(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id, status="pending_review"),
        )
        assert r.status_code == 201
        assert r.json()["status"] == "pending_review"

        notes = await client.get(
            "/api/v1/notifications", headers=auth_header(w.superadmin)
        )
        match = [
            n for n in notes.json()["items"]
            if n["type"] == "opportunity_submitted"
            and n.get("entity_id") == r.json()["id"]
        ]
        assert match
        # The admin should be able to tell it was a rep, and for whom.
        assert w.partner_co.name in match[0]["message"]
        assert "sales rep" in match[0]["message"]

    async def test_the_partner_field_is_required(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities", headers=auth_header(w.rep), json=payload()
        )
        assert r.status_code == 400
        assert r.json()["code"] == "PARTNER_REQUIRED"

    async def test_a_customer_company_cannot_hold_the_lock(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.customer_co.id),
        )
        assert r.status_code == 400
        assert r.json()["code"] == "NOT_A_CHANNEL_PARTNER"

    async def test_an_inactive_partner_cannot_register_new_business(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.inactive_co.id),
        )
        assert r.status_code == 400
        assert r.json()["code"] == "COMPANY_INACTIVE"

    async def test_an_unknown_partner_is_not_found(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(999_999_999),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# The lock is judged against the partner, not the rep
# ---------------------------------------------------------------------------

class TestExclusivityFollowsThePartner:
    async def _lock_customer_to(self, db, company_id, partner_id, customer):
        deal = await make_deal(
            db, company_id=company_id, registered_by=partner_id,
            status=DealStatus.APPROVED, customer=customer,
        )
        deal.exclusivity_start = date.today() - timedelta(days=10)
        deal.exclusivity_end = date.today() + timedelta(days=80)
        await db.commit()
        return deal

    async def test_another_partners_exclusivity_blocks_the_rep(self, client, db):
        w = await build(db)
        customer = unique("Locked Customer")
        await self._lock_customer_to(db, w.other_co.id, w.other_partner.id, customer)

        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id, customer_name=customer),
        )
        assert r.status_code == 409
        assert r.json()["code"] == "DUPLICATE_BLOCKED"

    async def test_the_incumbents_own_exclusivity_does_not_block_them(self, client, db):
        # Same customer, same rep — but registered for the partner who holds
        # the lock. Their own lock never blocks them.
        w = await build(db)
        customer = unique("Locked Customer")
        await self._lock_customer_to(db, w.other_co.id, w.other_partner.id, customer)

        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.other_co.id, customer_name=customer),
        )
        assert r.status_code == 201, r.text[:300]

    async def test_the_live_check_follows_the_chosen_partner(self, client, db):
        w = await build(db)
        customer = unique("Locked Customer")
        await self._lock_customer_to(db, w.other_co.id, w.other_partner.id, customer)

        as_rival = await client.post(
            "/api/v1/opportunities/check-duplicate",
            headers=auth_header(w.rep),
            json={"customer_name": customer, "country": "US", "company_id": w.partner_co.id},
        )
        assert as_rival.json()["severity"] == "block"

        as_incumbent = await client.post(
            "/api/v1/opportunities/check-duplicate",
            headers=auth_header(w.rep),
            json={"customer_name": customer, "country": "US", "company_id": w.other_co.id},
        )
        assert as_incumbent.json()["severity"] != "block"

    async def test_a_partner_cannot_use_the_check_to_impersonate_another(self, client, db):
        # The company field on the check is honoured for reps only. A partner
        # naming the incumbent must still see the block.
        w = await build(db)
        customer = unique("Locked Customer")
        await self._lock_customer_to(db, w.other_co.id, w.other_partner.id, customer)

        r = await client.post(
            "/api/v1/opportunities/check-duplicate",
            headers=auth_header(w.partner),
            json={"customer_name": customer, "country": "US", "company_id": w.other_co.id},
        )
        assert r.json()["severity"] == "block"


# ---------------------------------------------------------------------------
# Working the registration afterwards
# ---------------------------------------------------------------------------

class TestRepWorksTheirRegistration:
    async def _raise(self, client, w, **overrides):
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.rep),
            json=payload(w.partner_co.id, **overrides),
        )
        assert r.status_code == 201, r.text[:300]
        return r.json()["id"]

    async def test_the_rep_can_edit_their_draft(self, client, db):
        w = await build(db)
        opp_id = await self._raise(client, w)
        r = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.rep),
            json={"name": "Renamed by the rep"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["name"] == "Renamed by the rep"

    async def test_editing_cannot_move_it_off_the_rep(self, client, db):
        w = await build(db)
        opp_id = await self._raise(client, w)
        r = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.rep),
            json={"sales_rep_id": w.other_rep.id},
        )
        assert r.status_code == 200
        assert r.json()["sales_rep_id"] == w.rep.id

    async def test_the_rep_can_submit_it(self, client, db):
        w = await build(db)
        opp_id = await self._raise(client, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp_id}/submit", headers=auth_header(w.rep)
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "pending_review"

    async def test_another_rep_cannot_touch_it(self, client, db):
        w = await build(db)
        opp_id = await self._raise(client, w)
        edit = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.other_rep),
            json={"name": "hijacked"},
        )
        assert edit.status_code in (403, 404)
        submit = await client.post(
            f"/api/v1/opportunities/{opp_id}/submit", headers=auth_header(w.other_rep)
        )
        assert submit.status_code in (403, 404)

    async def test_the_partner_cannot_edit_the_reps_registration(self, client, db):
        # It is in their pipeline and they can read it; editing stays with
        # whoever raised it, as it does between two colleagues.
        w = await build(db)
        opp_id = await self._raise(client, w)
        r = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.partner),
            json={"name": "partner edit"},
        )
        assert r.status_code == 403

    async def test_a_rep_cannot_edit_a_partners_registration(self, client, db):
        # Assignment grants reading and the POC work, not the partner's pen.
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.partner_co.id, submitted_by=w.partner.id,
            status=OpportunityStatus.DRAFT,
        )
        opp.sales_rep_id = w.rep.id
        await db.commit()
        r = await client.put(
            f"/api/v1/opportunities/{opp.id}",
            headers=auth_header(w.rep),
            json={"name": "rep edit"},
        )
        assert r.status_code == 403

    async def test_the_admin_can_approve_it_like_any_other(self, client, db):
        w = await build(db)
        opp_id = await self._raise(client, w, status="pending_review")
        r = await client.post(
            f"/api/v1/opportunities/{opp_id}/approve",
            headers=auth_header(w.manager),
            json={},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "approved"
        assert r.json()["company_id"] == w.partner_co.id


# ---------------------------------------------------------------------------
# The pickers
# ---------------------------------------------------------------------------

class TestPickers:
    async def test_the_partner_list_is_the_live_programme(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/opportunities/partner-companies", headers=auth_header(w.rep)
        )
        assert r.status_code == 200
        ids = {c["id"] for c in r.json()}
        assert w.partner_co.id in ids
        assert w.other_co.id in ids
        # Neither can hold a lock, so neither is offered.
        assert w.customer_co.id not in ids
        assert w.inactive_co.id not in ids

    async def test_the_partner_list_says_what_each_one_is(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/opportunities/partner-companies", headers=auth_header(w.rep)
        )
        mine = next(c for c in r.json() if c["id"] == w.partner_co.id)
        assert mine["name"] == w.partner_co.name
        assert mine["company_type"] == "partner"
        assert mine["country"] == "US"

    async def test_known_customers_come_from_the_pipeline(self, client, db):
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.other_co.id, submitted_by=w.other_partner.id
        )
        await db.commit()
        r = await client.get(
            "/api/v1/opportunities/known-customers",
            params={"q": opp.customer_name},
            headers=auth_header(w.rep),
        )
        assert r.status_code == 200
        match = [c for c in r.json() if c["customer_name"] == opp.customer_name]
        assert len(match) == 1
        assert match[0]["country"] == "US"
        assert match[0]["company_name"] == w.other_co.name

    async def test_known_customers_include_customer_companies(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/opportunities/known-customers",
            params={"q": w.customer_co.name},
            headers=auth_header(w.rep),
        )
        names = {c["customer_name"] for c in r.json()}
        assert w.customer_co.name in names

    async def test_known_customers_are_deduplicated(self, client, db):
        w = await build(db)
        first = await make_opportunity(
            db, company_id=w.other_co.id, submitted_by=w.other_partner.id
        )
        # Same customer registered twice, once by each partner.
        second = await make_opportunity(
            db, company_id=w.partner_co.id, submitted_by=w.partner.id
        )
        second.customer_name = first.customer_name
        second.customer_name_normalized = first.customer_name_normalized
        await db.commit()
        r = await client.get(
            "/api/v1/opportunities/known-customers",
            params={"q": first.customer_name},
            headers=auth_header(w.rep),
        )
        assert [c["customer_name"] for c in r.json()].count(first.customer_name) == 1

    async def test_pickers_are_open_to_admins_too(self, client, db):
        w = await build(db)
        for path in ("/api/v1/opportunities/partner-companies",
                     "/api/v1/opportunities/known-customers"):
            r = await client.get(path, headers=auth_header(w.manager))
            assert r.status_code == 200, path
