"""Licences coming up for renewal.

The assertions worth reading are about what a renewal has to carry with it:
the deployment's details so nobody retypes them, a link back to the licence so
"did this customer renew" is answerable, and a deal registration so the
renewal actually pays the partner.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.deal_registration import DealRegistration, DealStatus
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_license,
    make_opportunity,
    make_user,
    requires_db,
)

pytestmark = requires_db
asyncio_test = pytest.mark.asyncio


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.manager = await make_user(db, role=UserRole.ADMIN)
    w.other_admin = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.manager.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.rep = await make_user(db, role=UserRole.SALES_REP)

    w.other_company = await make_company(db, channel_manager_id=w.other_admin.id)
    w.other_partner = await make_user(
        db, role=UserRole.PARTNER, company_id=w.other_company.id
    )
    await db.commit()
    return w


async def licensed(db, w, *, expires_in_days=45, **kwargs):
    """An approved deployment with a licence expiring N days out."""
    opp = await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner.id,
        status=OpportunityStatus.APPROVED,
        products=["MonetX"],
    )
    opp.sales_rep_id = w.rep.id
    opp.industry = "Banking"
    await db.flush()
    lic = await make_license(db, opportunity_id=opp.id, expires_in_days=expires_in_days, **kwargs)
    await db.commit()
    return opp, lic


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

class TestSweep:
    pytestmark = asyncio_test

    async def test_a_licence_inside_the_window_is_chased(self, client, db):
        from app.services.renewal_service import sweep_renewals

        w = await build(db)
        opp, lic = await licensed(db, w, expires_in_days=45)
        await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        assert lic.renewal_notified_at is not None

        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        assert any(n["type"] == "license_renewal_due" for n in notes.json()["items"])

    async def test_the_sales_rep_and_channel_manager_are_told_too(self, client, db):
        from app.services.renewal_service import sweep_renewals

        w = await build(db)
        await licensed(db, w, expires_in_days=30)
        await sweep_renewals(db)
        await db.commit()

        for actor in (w.rep, w.manager):
            notes = await client.get(
                "/api/v1/notifications", headers=auth_header(actor)
            )
            assert any(
                n["type"] == "license_renewal_due" for n in notes.json()["items"]
            ), actor.role

    async def test_a_licence_further_out_is_left_alone(self, client, db):
        from app.services.renewal_service import sweep_renewals

        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=300)
        await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        assert lic.renewal_notified_at is None

    async def test_an_expired_licence_is_not_chased(self, client, db):
        # Past its date there is nothing to renew in place — that is a new
        # deal, and a reminder now would only be noise.
        from app.services.renewal_service import sweep_renewals

        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=-1)
        await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        assert lic.renewal_notified_at is None

    async def test_the_chase_happens_once(self, client, db):
        from app.services.renewal_service import sweep_renewals

        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=45)
        await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        first = lic.renewal_notified_at

        await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        assert lic.renewal_notified_at == first

    async def test_a_licence_already_being_renewed_is_not_chased(self, client, db):
        # The work is underway; a reminder would read as a mistake.
        from app.services.renewal_service import create_renewal, sweep_renewals

        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=45)
        await create_renewal(db, lic.id, w.partner)
        await db.commit()

        result = await sweep_renewals(db)
        await db.commit()
        await db.refresh(lic)
        assert lic.renewal_notified_at is None
        assert result["notified"] == 0


# ---------------------------------------------------------------------------
# Raising the renewal
# ---------------------------------------------------------------------------

class TestCreateRenewal:
    pytestmark = asyncio_test

    async def _renewal_row(self, db, license_id):
        return (await db.execute(
            select(Opportunity).where(
                Opportunity.renewal_of_license_id == license_id
            )
        )).scalars().first()

    async def test_a_partner_can_raise_the_renewal(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w)
        r = await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["status"] == "draft"
        assert r.json()["renewal_of_license_id"] == lic.id

    async def test_the_deployment_details_carry_forward(self, client, db):
        # Retyping them is how a renewal ends up recorded as unrelated new
        # business.
        w = await build(db)
        opp, lic = await licensed(db, w)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.customer_name == opp.customer_name
        assert [l.product for l in renewal.products] == [
            l.product for l in opp.products
        ]
        assert renewal.industry == opp.industry
        assert renewal.country == opp.country
        assert renewal.company_id == opp.company_id
        assert renewal.sales_rep_id == opp.sales_rep_id

    async def test_the_current_sizing_is_recorded_on_the_renewal(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, device_count=120, node_count=8)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert "120 devices" in renewal.requirements
        assert "8 nodes" in renewal.requirements

    async def test_the_value_defaults_to_what_the_customer_pays_today(self, client, db):
        # The licence's PO value, not the original deal's worth, which may have
        # included one-off services that do not recur.
        from decimal import Decimal

        w = await build(db)
        opp, lic = await licensed(db, w, po_value=Decimal("31000.00"))
        assert opp.worth != Decimal("31000.00")

        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.worth == Decimal("31000.00")

    async def test_the_value_and_date_can_be_overridden(self, client, db):
        from decimal import Decimal

        w = await build(db)
        _, lic = await licensed(db, w)
        target = date.today() + timedelta(days=20)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner),
            json={"worth": 77000, "closing_date": str(target)},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.worth == Decimal("77000.00")
        assert renewal.closing_date == target

    async def test_the_product_lines_are_rescaled_to_an_overridden_value(
        self, client, db
    ):
        # The lines came from a deal worth X; if the renewal is agreed at Y the
        # lines have to move with it, or the breakdown stops adding up to the
        # deal. Also the path where an overridden float meets a stored Decimal.
        from decimal import Decimal

        w = await build(db)
        opp, lic = await licensed(db, w, po_value=Decimal("40000.00"))
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner),
            json={"worth": 80000},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.worth == Decimal("80000")
        # One line, originally the whole 40k, doubled with the deal.
        assert [l.value for l in renewal.products] == [Decimal("80000.00")]

    async def test_it_closes_by_the_expiry_date_by_default(self, client, db):
        # A renewal closing after the licence lapses is a gap in service.
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=40)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.closing_date == lic.license_expires_at

    async def test_a_deal_registration_is_created_so_it_earns_commission(
        self, client, db
    ):
        # Commission here is keyed to a deal registration. A renewal without
        # one pays the partner nothing, which is not a renewal anyone chases.
        w = await build(db)
        _, lic = await licensed(db, w)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        deal = (await db.execute(
            select(DealRegistration).where(
                DealRegistration.opportunity_id == renewal.id
            )
        )).scalars().first()
        assert deal is not None
        assert deal.status == DealStatus.PENDING
        assert deal.company_id == renewal.company_id
        assert deal.estimated_value == renewal.worth

    async def test_the_renewal_deal_pays_out_like_any_other(self, client, db):
        # The whole point of creating the registration: approving it runs the
        # ordinary commission engine at the company's current tier.
        from app.models.commission import Commission

        w = await build(db)
        _, lic = await licensed(db, w)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        renewal = await self._renewal_row(db, lic.id)
        deal = (await db.execute(
            select(DealRegistration).where(
                DealRegistration.opportunity_id == renewal.id
            )
        )).scalars().first()

        approved = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/approve",
            headers=auth_header(w.manager), json={"exclusivity_days": 90},
        )
        assert approved.status_code == 200, approved.text[:300]

        commission = (await db.execute(
            select(Commission).where(Commission.deal_id == deal.id)
        )).scalars().first()
        assert commission is not None
        assert commission.amount > 0

    async def test_an_admin_raising_it_leaves_the_deal_with_the_partner(
        self, client, db
    ):
        # The renewal belongs to the partner; an admin acting on their behalf
        # must not take it off them.
        w = await build(db)
        opp, lic = await licensed(db, w)
        r = await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.manager), json={},
        )
        assert r.status_code == 201, r.text[:300]
        renewal = await self._renewal_row(db, lic.id)
        assert renewal.submitted_by == opp.submitted_by

        deal = (await db.execute(
            select(DealRegistration).where(
                DealRegistration.opportunity_id == renewal.id
            )
        )).scalars().first()
        assert deal.registered_by == opp.submitted_by

    async def test_the_partner_is_told_when_somebody_else_raises_it(self, client, db):
        w = await build(db)
        await build(db)
        _, lic = await licensed(db, w)
        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.manager), json={},
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        assert any(n["type"] == "renewal_created" for n in notes.json()["items"])

    async def test_a_licence_cannot_be_renewed_twice(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w)
        headers = auth_header(w.partner)
        first = await client.post(f"/api/v1/renewals/{lic.id}", headers=headers, json={})
        assert first.status_code == 201
        second = await client.post(f"/api/v1/renewals/{lic.id}", headers=headers, json={})
        assert second.status_code == 409
        assert second.json()["code"] == "ALREADY_RENEWED"

    async def test_another_partner_cannot_renew_it(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w)
        r = await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.other_partner), json={},
        )
        assert r.status_code in (403, 404)

    async def test_an_out_of_scope_admin_cannot_renew_it(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w)
        r = await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.other_admin), json={},
        )
        assert r.status_code in (403, 404)

    async def test_the_renewal_says_what_it_renews(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w)
        created = await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        detail = await client.get(
            f"/api/v1/opportunities/{created.json()['id']}",
            headers=auth_header(w.partner),
        )
        assert detail.json()["renewal_of_license_id"] == lic.id


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------

class TestQueue:
    pytestmark = asyncio_test

    async def test_it_lists_licences_inside_the_window(self, client, db):
        w = await build(db)
        _, soon = await licensed(db, w, expires_in_days=30)
        _, later = await licensed(db, w, expires_in_days=400)

        r = await client.get("/api/v1/renewals", headers=auth_header(w.partner))
        assert r.status_code == 200, r.text[:300]
        ids = {row["license_id"] for row in r.json()}
        assert soon.id in ids
        assert later.id not in ids

    async def test_it_reports_the_days_left_and_the_sizing(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=30, device_count=99)
        r = await client.get("/api/v1/renewals", headers=auth_header(w.partner))
        row = next(x for x in r.json() if x["license_id"] == lic.id)
        assert row["days_left"] == 30
        assert row["device_count"] == 99

    async def test_it_says_whether_the_renewal_is_already_raised(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=30)
        before = await client.get("/api/v1/renewals", headers=auth_header(w.partner))
        assert next(
            x for x in before.json() if x["license_id"] == lic.id
        )["renewal_opportunity_id"] is None

        await client.post(
            f"/api/v1/renewals/{lic.id}", headers=auth_header(w.partner), json={},
        )
        after = await client.get("/api/v1/renewals", headers=auth_header(w.partner))
        assert next(
            x for x in after.json() if x["license_id"] == lic.id
        )["renewal_opportunity_id"] is not None

    async def test_a_partner_sees_only_their_own(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=30)
        r = await client.get("/api/v1/renewals", headers=auth_header(w.other_partner))
        assert lic.id not in {row["license_id"] for row in r.json()}

    async def test_an_out_of_scope_admin_sees_nothing_of_it(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=30)
        r = await client.get("/api/v1/renewals", headers=auth_header(w.other_admin))
        assert lic.id not in {row["license_id"] for row in r.json()}

    async def test_a_superadmin_sees_every_company(self, client, db):
        w = await build(db)
        _, lic = await licensed(db, w, expires_in_days=30)
        r = await client.get("/api/v1/renewals", headers=auth_header(w.superadmin))
        assert lic.id in {row["license_id"] for row in r.json()}

    async def test_a_sales_rep_is_kept_out_of_the_queue(self, client, db):
        w = await build(db)
        r = await client.get("/api/v1/renewals", headers=auth_header(w.rep))
        assert r.status_code in (403, 404)

    async def test_the_horizon_can_be_widened(self, client, db):
        w = await build(db)
        _, far = await licensed(db, w, expires_in_days=200)
        narrow = await client.get("/api/v1/renewals", headers=auth_header(w.partner))
        assert far.id not in {row["license_id"] for row in narrow.json()}

        wide = await client.get(
            "/api/v1/renewals?days=365", headers=auth_header(w.partner)
        )
        assert far.id in {row["license_id"] for row in wide.json()}
