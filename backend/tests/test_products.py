"""Products and sizing on an opportunity.

The assertions worth reading are about the two things a single `product`
column could not express: a deal that sells two products, and the sizing the
quote is built from. Plus the arithmetic that makes pipeline-by-product
trustworthy — a two-product deal must not report its whole value under both.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.opportunity import OpportunityStatus
from app.models.opportunity_product import PRODUCTS, OpportunityProduct
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
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
    w.company = await make_company(db, channel_manager_id=w.manager.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    await db.commit()
    return w


def _payload(**overrides):
    body = {
        "name": "Two-product deal",
        "customer_name": "Broadleaf Bank",
        "region": "MEA",
        "country": "UAE",
        "city": "Dubai",
        "worth": 200000,
        "closing_date": "2027-06-30",
        "requirements": "Monitoring and support across two datacentres.",
    }
    body.update(overrides)
    return body


class TestCatalogue:
    pytestmark = asyncio_test

    async def test_the_five_products_are_served(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/opportunities/products", headers=auth_header(w.partner)
        )
        assert r.status_code == 200, r.text[:300]
        assert [o["value"] for o in r.json()] == list(PRODUCTS)

    async def test_the_catalogue_covers_what_was_asked_for(self):
        assert set(PRODUCTS) == {
            "MonetX", "SupportX", "GreenX", "PatchX", "AgentX",
        }


class TestLines:
    pytestmark = asyncio_test

    async def test_a_deal_can_carry_several_products(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(products=[
                {"product": "MonetX", "device_count": 120, "node_count": 6, "value": 150000},
                {"product": "SupportX", "device_count": 120, "value": 50000},
            ]),
        )
        assert r.status_code == 201, r.text[:400]
        body = r.json()
        assert [line["product"] for line in body["products"]] == ["MonetX", "SupportX"]
        assert body["products"][0]["device_count"] == 120
        assert body["products"][0]["node_count"] == 6

    async def test_the_sizing_is_captured_before_the_po(self, client, db):
        # The whole point: device and node counts used to appear only on the
        # licence record, which is created after the PO lands.
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[
                {"product": "GreenX", "device_count": 40, "node_count": 3},
            ]),
        )
        assert created.status_code == 201, created.text[:300]
        line = created.json()["products"][0]
        assert (line["device_count"], line["node_count"]) == (40, 3)

    async def test_the_summary_names_the_biggest_line(self, client, db):
        # One word for the places that only have room for one, derived rather
        # than stored so it cannot disagree with the lines.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(products=[
                {"product": "SupportX", "value": 20000},
                {"product": "MonetX", "value": 180000},
            ]),
        )
        assert r.json()["product"] == "MonetX"

    async def test_an_invented_product_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(products=[{"product": "TurboX"}]),
        )
        assert r.status_code == 400
        assert r.json()["code"] == "UNKNOWN_PRODUCT"

    async def test_case_and_spacing_are_normalised(self, client, db):
        # Otherwise "monetx" and "MonetX" are two product lines in every
        # breakdown, which is the failure the old free-text column had.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(products=[{"product": "  monetx "}]),
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["products"][0]["product"] == "MonetX"

    async def test_the_same_product_cannot_be_listed_twice(self, client, db):
        # There is nothing a second MonetX line can say that the first cannot,
        # and two would double that product's pipeline.
        w = await build(db)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(products=[
                {"product": "MonetX", "value": 100000},
                {"product": "MonetX", "value": 100000},
            ]),
        )
        assert r.status_code in (400, 409, 422), r.text[:300]

    async def test_editing_replaces_the_whole_set(self, client, db):
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[
                {"product": "MonetX"}, {"product": "SupportX"},
            ]),
        )
        opp_id = created.json()["id"]
        updated = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.partner),
            json={"products": [{"product": "PatchX", "device_count": 10}]},
        )
        assert updated.status_code == 200, updated.text[:300]
        assert [l["product"] for l in updated.json()["products"]] == ["PatchX"]

    async def test_an_edit_that_does_not_mention_products_leaves_them_alone(
        self, client, db
    ):
        # An update built from a form that only changes the closing date must
        # not silently strip the product lines.
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[{"product": "AgentX"}]),
        )
        opp_id = created.json()["id"]
        updated = await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.partner),
            json={"closing_date": "2027-09-30"},
        )
        assert [l["product"] for l in updated.json()["products"]] == ["AgentX"]

    async def test_an_empty_list_clears_them(self, client, db):
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[{"product": "AgentX"}]),
        )
        updated = await client.put(
            f"/api/v1/opportunities/{created.json()['id']}",
            headers=auth_header(w.partner),
            json={"products": []},
        )
        assert updated.json()["products"] == []
        assert updated.json()["product"] is None

    async def test_lines_go_when_the_opportunity_does(self, client, db):
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            products=["MonetX"],
        )
        await db.commit()
        opp_id = opp.id

        await db.delete(opp)
        await db.commit()

        left = (await db.execute(
            select(OpportunityProduct).where(
                OpportunityProduct.opportunity_id == opp_id
            )
        )).scalars().all()
        assert left == []


class TestFiltering:
    pytestmark = asyncio_test

    async def test_the_filter_finds_a_deal_by_any_of_its_products(self, client, db):
        # A two-product deal used to be findable only under whichever one the
        # single column happened to hold.
        w = await build(db)
        both = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
            products=[("MonetX", Decimal("60000")), ("GreenX", Decimal("40000"))],
        )
        await db.commit()

        for product in ("MonetX", "GreenX"):
            r = await client.get(
                f"/api/v1/opportunities?product={product}&company_id={w.company.id}",
                headers=auth_header(w.superadmin),
            )
            assert both.id in {i["id"] for i in r.json()["items"]}, product

    async def test_the_list_shows_every_product_on_the_deal(self, client, db):
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
            products=[("MonetX", Decimal("60000")), ("GreenX", Decimal("40000"))],
        )
        await db.commit()
        r = await client.get(
            f"/api/v1/opportunities?company_id={w.company.id}",
            headers=auth_header(w.superadmin),
        )
        row = next(i for i in r.json()["items"] if i["id"] == opp.id)
        assert set(row["products"]) == {"MonetX", "GreenX"}


class TestPipelineByProduct:
    pytestmark = asyncio_test

    async def _breakdown(self, client, actor):
        r = await client.get(
            "/api/v1/dashboard/admin/target-plan", headers=auth_header(actor)
        )
        assert r.status_code == 200, r.text[:300]
        return {b["product"]: b for b in r.json()["by_product"]}

    async def test_a_two_product_deal_is_split_not_doubled(self, client, db):
        # Attributing the whole deal to both products would make the columns
        # add up to more than the pipeline.
        w = await build(db)
        before = await self._breakdown(client, w.superadmin)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
            products=[("MonetX", Decimal("60000")), ("GreenX", Decimal("40000"))],
        )
        await db.commit()

        after = await self._breakdown(client, w.superadmin)
        monet = Decimal(after["MonetX"]["total_worth"]) - Decimal(
            before.get("MonetX", {"total_worth": 0})["total_worth"]
        )
        green = Decimal(after["GreenX"]["total_worth"]) - Decimal(
            before.get("GreenX", {"total_worth": 0})["total_worth"]
        )
        assert monet == Decimal("60000")
        assert green == Decimal("40000")

    async def test_money_on_no_product_line_is_reported_as_unattributed(
        self, client, db
    ):
        # Rather than vanishing from the breakdown, which would make it
        # disagree with the headline pipeline number.
        w = await build(db)
        before = await self._breakdown(client, w.superadmin)
        base = Decimal(before.get("Unattributed", {"total_worth": 0})["total_worth"])

        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
            products=[("MonetX", Decimal("20000"))],
        )
        opp.worth = Decimal("50000")  # 30k of services on no product line
        await db.commit()

        after = await self._breakdown(client, w.superadmin)
        assert Decimal(after["Unattributed"]["total_worth"]) - base == Decimal("30000")

    async def test_the_breakdown_reconciles_with_total_pipeline(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
            products=[("PatchX", Decimal("15000"))],
        )
        await db.commit()

        r = await client.get(
            "/api/v1/dashboard/admin/target-plan", headers=auth_header(w.superadmin)
        )
        body = r.json()
        total = Decimal(body["total_worth"])
        summed = sum(Decimal(b["total_worth"]) for b in body["by_product"])
        assert summed == total


class TestAuditSerialisation:
    """A latent bug this work surfaced.

    Audit metadata is built from model attributes, so it carries dates and
    Decimals, and it lands in a JSON column that is serialised at flush time —
    inside the request. Editing an opportunity's closing date or worth did not
    write a bad audit row, it raised and failed the whole edit.
    """

    pytestmark = asyncio_test

    async def test_editing_the_closing_date_succeeds(self, client, db):
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[{"product": "MonetX"}]),
        )
        r = await client.put(
            f"/api/v1/opportunities/{created.json()['id']}",
            headers=auth_header(w.partner),
            json={"closing_date": "2027-12-31"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["closing_date"] == "2027-12-31"

    async def test_editing_the_worth_succeeds(self, client, db):
        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[{"product": "MonetX"}]),
        )
        r = await client.put(
            f"/api/v1/opportunities/{created.json()['id']}",
            headers=auth_header(w.partner),
            json={"worth": 275000},
        )
        assert r.status_code == 200, r.text[:300]
        assert Decimal(r.json()["worth"]) == Decimal("275000")

    async def test_the_audit_row_keeps_the_values(self, client, db):
        # Not just "it did not crash": the point of the row is what changed.
        from app.models.audit_log import AuditLog

        w = await build(db)
        created = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_payload(status="draft", products=[{"product": "MonetX"}]),
        )
        opp_id = created.json()["id"]
        await client.put(
            f"/api/v1/opportunities/{opp_id}",
            headers=auth_header(w.partner),
            json={"worth": 275000},
        )

        row = (await db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "opportunity", AuditLog.entity_id == opp_id)
            .order_by(AuditLog.id.desc())
        )).scalars().first()
        assert row is not None
        # Money as a string, so the audit trail does not round it.
        assert row.metadata_json["after"]["worth"] == "275000"

    async def test_a_decimal_is_not_rounded_into_a_float(self):
        from app.utils.audit import _json_safe

        assert _json_safe(Decimal("0.1")) == "0.1"
        assert _json_safe({"a": Decimal("1.005")}) == {"a": "1.005"}
