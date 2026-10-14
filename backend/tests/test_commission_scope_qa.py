"""Channel-manager scope on the commission and statement routes (QA findings).

The module used to scope partners only and let every admin through as if a
superadmin: an out-of-scope channel manager could read any commission by id,
change its status, and list / download every company's statements. These
tests pin the fix: superadmin sees all, a channel manager only the companies
they manage (primary or co-manager), a partner only their own.

Denials on /commissions/{id} are 404 (the module does not confirm a commission
exists to someone who may not see it); statement routes keyed by company id
give the same 403 as the scorecard.
"""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from app.models.commission import Commission, CommissionStatus
from app.models.company import PartnerTier, company_channel_managers
from app.models.deal_registration import DealStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_deal,
    make_user,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.asyncio]

PERIOD = "2026-03"
CALCULATED_AT = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)


async def _make_commission(db, *, company_id, user_id, status=CommissionStatus.APPROVED):
    deal = await make_deal(
        db, company_id=company_id, registered_by=user_id, status=DealStatus.APPROVED
    )
    c = Commission(
        deal_id=deal.id,
        company_id=company_id,
        user_id=user_id,
        tier_at_calculation=PartnerTier.SILVER,
        rate_percentage=Decimal("5.00"),
        deal_value=Decimal("100000.00"),
        amount=Decimal("5000.00"),
        currency="USD",
        status=status,
        calculated_at=CALCULATED_AT,
    )
    db.add(c)
    await db.flush()
    return c


@pytest.fixture
async def w(db):
    """A fresh world per test: status-changing tests mutate commissions."""
    x = SimpleNamespace()
    superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    manager_a = await make_user(db, role=UserRole.ADMIN)
    manager_b = await make_user(db, role=UserRole.ADMIN)
    co_manager = await make_user(db, role=UserRole.ADMIN)

    company_a = await make_company(db, channel_manager_id=manager_a.id)
    company_b = await make_company(db, channel_manager_id=manager_b.id)
    # co_manager is an *additional* manager of company_b, not the primary one.
    await db.execute(
        insert(company_channel_managers).values(company_id=company_b.id, user_id=co_manager.id)
    )

    partner_a = await make_user(db, role=UserRole.PARTNER, company_id=company_a.id)
    partner_b = await make_user(db, role=UserRole.PARTNER, company_id=company_b.id)

    comm_a = await _make_commission(db, company_id=company_a.id, user_id=partner_a.id)
    comm_b = await _make_commission(db, company_id=company_b.id, user_id=partner_b.id)
    pending_b = await _make_commission(
        db, company_id=company_b.id, user_id=partner_b.id, status=CommissionStatus.PENDING
    )
    await db.commit()

    x.company_a, x.company_b = company_a.id, company_b.id
    x.comm_a, x.comm_b, x.pending_b = comm_a.id, comm_b.id, pending_b.id
    x.hdr = {
        "superadmin": auth_header(superadmin),
        "manager_a": auth_header(manager_a),
        "manager_b": auth_header(manager_b),
        "co_manager": auth_header(co_manager),
        "partner_a": auth_header(partner_a),
    }
    return x


class TestCommissionById:
    async def test_out_of_scope_manager_cannot_read(self, client, w):
        r = await client.get(f"/api/v1/commissions/{w.comm_b}", headers=w.hdr["manager_a"])
        assert r.status_code == 404

    @pytest.mark.parametrize("who", ["manager_b", "co_manager", "superadmin"])
    async def test_in_scope_admins_can_read(self, client, w, who):
        r = await client.get(f"/api/v1/commissions/{w.comm_b}", headers=w.hdr[who])
        assert r.status_code == 200
        assert r.json()["company_id"] == w.company_b

    async def test_partner_still_scoped(self, client, w):
        hdr = w.hdr["partner_a"]
        assert (await client.get(f"/api/v1/commissions/{w.comm_a}", headers=hdr)).status_code == 200
        assert (await client.get(f"/api/v1/commissions/{w.comm_b}", headers=hdr)).status_code == 404


class TestStatusChange:
    async def test_out_of_scope_manager_cannot_change_status(self, client, w, db):
        r = await client.patch(
            f"/api/v1/commissions/{w.pending_b}/status",
            headers=w.hdr["manager_a"],
            json={"status": "approved"},
        )
        assert r.status_code == 404
        # And nothing changed underneath.
        r = await client.get(f"/api/v1/commissions/{w.pending_b}", headers=w.hdr["superadmin"])
        assert r.json()["status"] == "pending"

    async def test_co_manager_can_change_status(self, client, w):
        r = await client.patch(
            f"/api/v1/commissions/{w.pending_b}/status",
            headers=w.hdr["co_manager"],
            json={"status": "approved", "notes": "ok"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    async def test_superadmin_can_change_status(self, client, w):
        r = await client.patch(
            f"/api/v1/commissions/{w.comm_a}/status",
            headers=w.hdr["superadmin"],
            json={"status": "paid"},
        )
        assert r.status_code == 200
        assert r.json()["paid_at"] is not None

    async def test_partner_cannot_change_status(self, client, w):
        r = await client.patch(
            f"/api/v1/commissions/{w.comm_a}/status",
            headers=w.hdr["partner_a"],
            json={"status": "paid"},
        )
        assert r.status_code == 403

    @pytest.mark.parametrize("value", ["foo", "pending", "PAID", ""])
    async def test_nonsense_status_is_422(self, client, w, value):
        r = await client.patch(
            f"/api/v1/commissions/{w.comm_b}/status",
            headers=w.hdr["superadmin"],
            json={"status": value},
        )
        assert r.status_code == 422

    async def test_paid_is_final(self, client, w):
        hdr = w.hdr["superadmin"]
        url = f"/api/v1/commissions/{w.comm_b}/status"
        assert (await client.patch(url, headers=hdr, json={"status": "paid"})).status_code == 200
        for target in ("approved", "void", "paid"):
            r = await client.patch(url, headers=hdr, json={"status": target, "notes": "undo"})
            assert r.status_code == 400
            assert r.json()["code"] == "INVALID_TRANSITION"

    async def test_cannot_skip_approval(self, client, w):
        r = await client.patch(
            f"/api/v1/commissions/{w.pending_b}/status",
            headers=w.hdr["superadmin"],
            json={"status": "paid"},
        )
        assert r.status_code == 400


class TestCommissionList:
    async def test_manager_sees_only_managed(self, client, w):
        r = await client.get("/api/v1/commissions?page_size=100", headers=w.hdr["manager_a"])
        assert r.status_code == 200
        assert {i["company_id"] for i in r.json()["items"]} == {w.company_a}

    async def test_company_filter_outside_scope_is_empty(self, client, w):
        r = await client.get(
            f"/api/v1/commissions?company_id={w.company_b}", headers=w.hdr["manager_a"]
        )
        assert r.status_code == 200
        assert r.json()["total"] == 0

    async def test_invalid_status_filter_is_422_not_500(self, client, w):
        r = await client.get("/api/v1/commissions?status=foo", headers=w.hdr["superadmin"])
        assert r.status_code == 422

    async def test_valid_status_filter(self, client, w):
        r = await client.get(
            "/api/v1/commissions?status=pending&page_size=100", headers=w.hdr["manager_b"]
        )
        assert r.status_code == 200
        assert [i["id"] for i in r.json()["items"]] == [w.pending_b]


class TestStatements:
    async def test_list_scoped_to_managed_companies(self, client, w):
        r = await client.get("/api/v1/commissions/statements/list", headers=w.hdr["manager_a"])
        assert r.status_code == 200
        assert {s["company_id"] for s in r.json()} == {w.company_a}

    async def test_list_company_filter_outside_scope_is_empty(self, client, w):
        r = await client.get(
            f"/api/v1/commissions/statements/list?company_id={w.company_b}",
            headers=w.hdr["manager_a"],
        )
        assert r.status_code == 200
        assert r.json() == []

    async def test_superadmin_lists_everything(self, client, w):
        r = await client.get("/api/v1/commissions/statements/list", headers=w.hdr["superadmin"])
        ids = {s["company_id"] for s in r.json()}
        assert {w.company_a, w.company_b} <= ids

    async def test_out_of_scope_pdf_is_403(self, client, w):
        r = await client.get(
            f"/api/v1/commissions/statements/{w.company_b}/{PERIOD}.pdf",
            headers=w.hdr["manager_a"],
        )
        assert r.status_code == 403

    @pytest.mark.parametrize("who", ["manager_b", "co_manager", "superadmin"])
    async def test_in_scope_pdf(self, client, w, who):
        r = await client.get(
            f"/api/v1/commissions/statements/{w.company_b}/{PERIOD}.pdf",
            headers=w.hdr[who],
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    async def test_partner_pdf_own_only(self, client, w):
        hdr = w.hdr["partner_a"]
        own = await client.get(f"/api/v1/commissions/statements/{w.company_a}/{PERIOD}.pdf", headers=hdr)
        other = await client.get(f"/api/v1/commissions/statements/{w.company_b}/{PERIOD}.pdf", headers=hdr)
        assert own.status_code == 200
        assert other.status_code == 403

    async def test_nonexistent_company_pdf_is_404(self, client, w):
        r = await client.get(
            f"/api/v1/commissions/statements/99999999/{PERIOD}.pdf",
            headers=w.hdr["superadmin"],
        )
        assert r.status_code == 404
