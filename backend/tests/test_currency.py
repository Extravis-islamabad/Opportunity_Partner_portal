"""Deals in more than one currency, reported in one.

The assertion that matters most is the one about history: a rate change must
change what future deals are worth and leave recorded ones alone. Everything
else follows from storing the rate on the row instead of converting at read
time.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.currency import REPORTING_CURRENCY, Currency, CurrencyRate
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
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
    w.manager = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.manager.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    await db.commit()
    return w


def _payload(**overrides):
    body = {
        "name": "Regional deal",
        "customer_name": unique("Gulf Logistics"),
        "region": "MEA",
        "country": "UAE",
        "city": "Dubai",
        "worth": 100000,
        "closing_date": "2027-06-30",
        "requirements": "Regional rollout.",
        "status": "draft",
    }
    body.update(overrides)
    return body


async def _reload(db, opp_id):
    row = (await db.execute(
        select(Opportunity).where(Opportunity.id == opp_id)
    )).scalar_one()
    await db.refresh(row)
    return row


class TestRates:
    pytestmark = asyncio_test

    async def test_every_currency_is_listed_with_a_rate(self, client, db):
        w = await build(db)
        r = await client.get("/api/v1/currencies", headers=auth_header(w.partner))
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["reporting_currency"] == REPORTING_CURRENCY.value
        assert {c["currency"] for c in body["currencies"]} == {
            "USD", "SAR", "AED", "PKR",
        }

    async def test_the_reporting_currency_is_always_one(self, client, db):
        w = await build(db)
        r = await client.get("/api/v1/currencies", headers=auth_header(w.partner))
        usd = next(c for c in r.json()["currencies"] if c["currency"] == "USD")
        assert Decimal(usd["rate_to_usd"]) == Decimal("1")
        assert usd["is_reporting_currency"] is True

    async def test_a_superadmin_can_publish_a_rate(self, client, db):
        w = await build(db)
        r = await client.put(
            "/api/v1/currencies/PKR",
            headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0034"},
        )
        assert r.status_code == 200, r.text[:300]
        assert Decimal(r.json()["rate_to_usd"]) == Decimal("0.0034")

    async def test_a_channel_manager_cannot(self, client, db):
        w = await build(db)
        r = await client.put(
            "/api/v1/currencies/PKR",
            headers=auth_header(w.manager),
            json={"rate_to_usd": "0.0034"},
        )
        assert r.status_code in (403, 404)

    async def test_a_partner_cannot(self, client, db):
        w = await build(db)
        r = await client.put(
            "/api/v1/currencies/AED",
            headers=auth_header(w.partner),
            json={"rate_to_usd": "9"},
        )
        assert r.status_code in (403, 404)

    async def test_the_reporting_currency_rate_cannot_be_changed(self, client, db):
        # It is 1 by definition; a settable value would let somebody make
        # dollars worth something other than dollars.
        w = await build(db)
        r = await client.put(
            "/api/v1/currencies/USD",
            headers=auth_header(w.superadmin),
            json={"rate_to_usd": "1.2"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "REPORTING_CURRENCY_FIXED"

    async def test_publishing_closes_the_previous_rate(self, client, db):
        # Dated rather than overwritten, so the rate a deal used can still be
        # explained after it changes.
        w = await build(db)
        await client.put(
            "/api/v1/currencies/SAR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.2700"},
        )
        await client.put(
            "/api/v1/currencies/SAR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.2650"},
        )
        rows = (await db.execute(
            select(CurrencyRate).where(CurrencyRate.currency == Currency.SAR)
        )).scalars().all()
        open_rows = [r for r in rows if r.effective_to is None]
        assert len(open_rows) == 1, "only one rate can be current"
        assert Decimal(open_rows[0].rate_to_usd) == Decimal("0.2650")

    async def test_a_zero_rate_is_refused(self, client, db):
        # It would value every deal in that currency at nothing.
        w = await build(db)
        r = await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0"},
        )
        assert r.status_code == 422


class TestConversion:
    pytestmark = asyncio_test

    async def test_a_deal_records_its_currency_and_rate(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=100000, currency="AED"),
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["currency"] == "AED"

        row = await _reload(db, r.json()["id"])
        assert row.currency == Currency.AED
        assert row.exchange_rate_to_usd > 0

    async def test_the_reporting_value_is_the_converted_one(self, client, db):
        w = await build(db)
        await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0036"},
        )
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=1000000, currency="PKR"),
        )
        # A million rupees is not a million dollars.
        assert Decimal(r.json()["worth_usd"]) == Decimal("3600.00")
        assert Decimal(r.json()["worth"]) == Decimal("1000000")

    async def test_an_unstated_currency_is_the_reporting_one(self, client, db):
        # Everything recorded before multi-currency existed was implicitly USD.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=5000),
        )
        assert r.json()["currency"] == "USD"
        assert Decimal(r.json()["worth_usd"]) == Decimal("5000.00")

    async def test_a_currency_with_no_published_rate_falls_back_sensibly(
        self, client, db
    ):
        # A missing rate is a configuration problem. Returning zero would value
        # every deal in that currency at nothing — silently, and expensively.
        from sqlalchemy import delete

        w = await build(db)
        await db.execute(
            delete(CurrencyRate).where(CurrencyRate.currency == Currency.AED)
        )
        await db.commit()

        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=100000, currency="AED"),
        )
        assert r.status_code == 201, r.text[:300]
        row = await _reload(db, r.json()["id"])
        assert row.exchange_rate_to_usd > 0, "a missing rate valued the deal at zero"
        assert Decimal(r.json()["worth_usd"]) > 0

    async def test_an_invented_currency_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(currency="XYZ"),
        )
        assert r.status_code == 422

    async def test_changing_the_currency_restamps_the_rate(self, client, db):
        # A row whose currency moved without its rate would report riyals
        # converted at the dollar rate.
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=100000),
        )
        opp_id = created.json()["id"]
        updated = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.partner),
            json={"currency": "SAR"},
        )
        assert updated.status_code == 200, updated.text[:300]
        row = await _reload(db, opp_id)
        assert row.currency == Currency.SAR
        assert row.exchange_rate_to_usd != Decimal("1")
        assert row.worth_usd < row.worth

    async def test_a_recorded_deal_keeps_its_rate_when_the_rate_moves(
        self, client, db
    ):
        # The whole reason the rate lives on the row: a report of last
        # quarter's business must not move because today's rate did.
        w = await build(db)
        await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0036"},
        )
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(worth=1000000, currency="PKR"),
        )
        opp_id = created.json()["id"]
        before = (await _reload(db, opp_id)).worth_usd

        # The rupee halves.
        await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0018"},
        )
        after = (await _reload(db, opp_id)).worth_usd
        assert after == before, "a recorded deal was restated by a later rate change"

    async def test_a_new_deal_uses_the_new_rate(self, client, db):
        # The other half: the change has to apply to something.
        w = await build(db)
        await client.put(
            "/api/v1/currencies/AED", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.2723"},
        )
        first = await client.post(
            "/api/v1/opportunities", headers=auth_header(w.partner),
            json=_payload(worth=100000, currency="AED"),
        )
        await client.put(
            "/api/v1/currencies/AED", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.1000"},
        )
        second = await client.post(
            "/api/v1/opportunities", headers=auth_header(w.partner),
            json=_payload(worth=100000, currency="AED"),
        )
        assert Decimal(second.json()["worth_usd"]) < Decimal(first.json()["worth_usd"])
        assert Decimal(second.json()["worth_usd"]) == Decimal("10000.00")


class TestReporting:
    pytestmark = asyncio_test

    async def test_pipeline_totals_are_in_the_reporting_currency(self, client, db):
        # The failure this replaces: a 500,000 PKR deal and a 500,000 USD deal
        # adding up to a million of nothing.
        w = await build(db)
        await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0036"},
        )

        analytics = await client.get(
            "/api/v1/dashboard/admin/target-plan", headers=auth_header(w.superadmin)
        )
        before = Decimal(analytics.json()["total_worth"])

        for currency, worth in (("USD", 10000), ("PKR", 1000000)):
            await client.post(
                "/api/v1/opportunities",
                headers=auth_header(w.partner),
                json=_payload(worth=worth, currency=currency, status="draft"),
            )

        analytics = await client.get(
            "/api/v1/dashboard/admin/target-plan", headers=auth_header(w.superadmin)
        )
        after = Decimal(analytics.json()["total_worth"])
        # 10,000 USD + (1,000,000 PKR = 3,600 USD)
        assert after - before == Decimal("13600.00")

    async def test_commission_is_earned_on_the_reporting_value(self, client, db):
        # Otherwise a PKR deal and a USD deal of the same face number pay the
        # same, which overpays one of them by a factor of 275.
        from app.models.commission import Commission
        from app.models.deal_registration import DealRegistration

        w = await build(db)
        await client.put(
            "/api/v1/currencies/PKR", headers=auth_header(w.superadmin),
            json={"rate_to_usd": "0.0036"},
        )
        created = await client.post(
            "/api/v1/dashboard/deals",
            headers=auth_header(w.partner),
            json={
                # Unique per run: registering a deal grants exclusivity on the
                # customer, so a fixed name is blocked by whatever an earlier
                # run of this test registered.
                "customer_name": unique("Karachi Freight"),
                "deal_description": "Rollout",
                "estimated_value": 1000000,
                "currency": "PKR",
                "expected_close_date": "2027-06-30",
            },
        )
        assert created.status_code == 201, created.text[:300]
        deal_id = created.json()["id"]

        approved = await client.post(
            f"/api/v1/dashboard/deals/{deal_id}/approve",
            headers=auth_header(w.manager), json={"exclusivity_days": 90},
        )
        assert approved.status_code == 200, approved.text[:300]

        commission = (await db.execute(
            select(Commission).where(Commission.deal_id == deal_id)
        )).scalars().first()
        deal = (await db.execute(
            select(DealRegistration).where(DealRegistration.id == deal_id)
        )).scalars().first()

        # 5% of $3,600, not 5% of 1,000,000.
        assert deal.estimated_value_usd == Decimal("3600.00")
        assert commission.amount < Decimal("1000")
