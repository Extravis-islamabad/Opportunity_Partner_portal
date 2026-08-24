"""Exclusivity windows ending, and partners asking for more time.

The assertions are about consequences: that a lapsed registration stops
reading as approved, that granting an extension moves the block along with
the window rather than leaving customer ownership expiring on the old date,
and that a partner cannot reach another partner's registration.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.customer_ownership import CustomerOwnership
from app.models.deal_extension import DealExtensionRequest, ExtensionStatus
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_deal,
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

    w.other_company = await make_company(db, channel_manager_id=w.other_admin.id)
    w.other_partner = await make_user(
        db, role=UserRole.PARTNER, company_id=w.other_company.id
    )
    await db.commit()
    return w


async def approved_deal(db, w, *, ends_in_days: int):
    """An approved registration whose window closes N days from today."""
    deal = await make_deal(
        db, company_id=w.company.id, registered_by=w.partner.id,
        status=DealStatus.APPROVED,
    )
    deal.exclusivity_start = date.today() - timedelta(days=30)
    deal.exclusivity_end = date.today() + timedelta(days=ends_in_days)
    await db.commit()
    return deal


async def reload(db, deal_id):
    row = (await db.execute(
        select(DealRegistration).where(DealRegistration.id == deal_id)
    )).scalar_one()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

class TestSweep:
    pytestmark = asyncio_test

    async def test_a_window_with_time_left_is_left_alone(self, client, db):
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=60)
        await sweep_exclusivity(db)
        await db.commit()

        row = await reload(db, deal.id)
        assert row.status == DealStatus.APPROVED
        assert row.expiry_warned_at is None

    async def test_a_window_closing_soon_warns_the_partner(self, client, db):
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await sweep_exclusivity(db)
        await db.commit()

        row = await reload(db, deal.id)
        assert row.expiry_warned_at is not None
        assert row.status == DealStatus.APPROVED, "warning must not expire it early"

        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        assert any(n["type"] == "exclusivity_expiring" for n in notes.json()["items"])

    async def test_the_channel_manager_is_warned_too(self, client, db):
        # Losing a customer's protection is the manager's problem as well, and
        # they are the one who can grant more time.
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        await approved_deal(db, w, ends_in_days=3)
        await sweep_exclusivity(db)
        await db.commit()

        notes = await client.get("/api/v1/notifications", headers=auth_header(w.manager))
        assert any(n["type"] == "exclusivity_expiring" for n in notes.json()["items"])

    async def test_the_warning_is_sent_once(self, client, db):
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await sweep_exclusivity(db)
        await db.commit()
        first = (await reload(db, deal.id)).expiry_warned_at

        await sweep_exclusivity(db)
        await db.commit()
        assert (await reload(db, deal.id)).expiry_warned_at == first

    async def test_a_window_ending_today_still_protects(self, client, db):
        # The end date is inclusive — duplicate_service blocks while
        # exclusivity_end >= today — so expiring on the last day would take
        # protection away a day early.
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=0)
        await sweep_exclusivity(db)
        await db.commit()

        row = await reload(db, deal.id)
        assert row.status == DealStatus.APPROVED
        assert row.expired_at is None
        assert row.expiry_warned_at is not None, "the last day is still a warning"

    async def test_a_lapsed_window_expires_the_registration(self, client, db):
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        await sweep_exclusivity(db)
        await db.commit()

        row = await reload(db, deal.id)
        assert row.status == DealStatus.EXPIRED
        assert row.expired_at is not None

        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        assert any(n["type"] == "exclusivity_expired" for n in notes.json()["items"])

    async def test_expiring_does_not_happen_twice(self, client, db):
        # The second sweep must not find it again: an expired registration is
        # no longer approved, so it is outside the query.
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        await sweep_exclusivity(db)
        await db.commit()
        stamped = (await reload(db, deal.id)).expired_at

        await sweep_exclusivity(db)
        await db.commit()
        assert (await reload(db, deal.id)).expired_at == stamped

    async def test_a_short_window_expires_without_a_warning_gap(self, client, db):
        # A window granted for fewer days than the warning period never gets
        # to be "about to expire". It must still expire, and must not be left
        # looking permanently un-warned.
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        await sweep_exclusivity(db)
        await db.commit()

        row = await reload(db, deal.id)
        assert row.status == DealStatus.EXPIRED
        assert row.expiry_warned_at is not None


# ---------------------------------------------------------------------------
# Customer ownership follows the window
# ---------------------------------------------------------------------------

class TestOwnership:
    pytestmark = asyncio_test

    async def _ownership_for(self, db, deal):
        return (await db.execute(
            select(CustomerOwnership).where(CustomerOwnership.source_deal_id == deal.id)
        )).scalar_one_or_none()

    async def test_expiry_releases_the_customer(self, client, db):
        from app.services import duplicate_service
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        await duplicate_service.upsert_ownership_from_deal(db, deal)
        await db.commit()

        assert (await self._ownership_for(db, deal)).is_active is True

        await sweep_exclusivity(db)
        await db.commit()
        own = await self._ownership_for(db, deal)
        await db.refresh(own)
        assert own.is_active is False

    async def test_expiry_does_not_release_a_customer_still_protected(self, client, db):
        # A later registration may have pushed valid_until further out. Letting
        # this deal's expiry deactivate the row would hand the customer away
        # while another window is still open.
        from app.services import duplicate_service
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        await duplicate_service.upsert_ownership_from_deal(db, deal)
        own = await self._ownership_for(db, deal)
        own.valid_until = date.today() + timedelta(days=60)
        await db.commit()

        await sweep_exclusivity(db)
        await db.commit()
        await db.refresh(own)
        assert own.is_active is True


# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------

class TestExtensions:
    pytestmark = asyncio_test

    async def test_a_partner_can_ask_for_more_time(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        r = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner),
            json={"days": 30, "reason": "Procurement slipped a quarter"},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["status"] == "pending"

    async def test_the_decider_is_told(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.manager))
        assert any(
            n["type"] == "exclusivity_extension_requested" for n in notes.json()["items"]
        )

    async def test_only_one_request_can_be_open_at_a_time(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        headers = auth_header(w.partner)
        first = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension", headers=headers,
            json={"days": 30},
        )
        assert first.status_code == 201
        second = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension", headers=headers,
            json={"days": 60},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "EXTENSION_ALREADY_REQUESTED"

    async def test_an_expired_registration_cannot_be_extended(self, client, db):
        # Once the protection is gone the deal has to be registered again —
        # extending would silently re-take a customer somebody else may have
        # registered in the meantime.
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=-1)
        deal.status = DealStatus.EXPIRED
        await db.commit()

        r = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "DEAL_NOT_EXCLUSIVE"

    async def test_another_partner_cannot_see_or_extend_the_deal(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        r = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.other_partner), json={"days": 30},
        )
        assert r.status_code in (403, 404)

    async def test_approving_moves_the_end_date(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        original_end = deal.exclusivity_end

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        req_id = created.json()["id"]

        r = await client.post(
            f"/api/v1/dashboard/deals/extensions/{req_id}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["granted_days"] == 30

        row = await reload(db, deal.id)
        assert row.exclusivity_end == original_end + timedelta(days=30)

    async def test_the_extension_runs_from_the_old_end_not_from_today(self, client, db):
        # Deciding late must not quietly shorten the protection granted.
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=10)

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )
        row = await reload(db, deal.id)
        assert row.exclusivity_end == date.today() + timedelta(days=40)

    async def test_approving_clears_the_warning_so_it_fires_again(self, client, db):
        from app.services.exclusivity_service import sweep_exclusivity

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await sweep_exclusivity(db)
        await db.commit()
        assert (await reload(db, deal.id)).expiry_warned_at is not None

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 90},
        )
        await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )
        assert (await reload(db, deal.id)).expiry_warned_at is None

    async def test_the_block_moves_with_the_window(self, client, db):
        # Extending the registration without extending customer ownership
        # would let the block lapse on the old date while the registration
        # claims the new one.
        from app.services import duplicate_service

        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await duplicate_service.upsert_ownership_from_deal(db, deal)
        await db.commit()

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 45},
        )
        await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )

        own = (await db.execute(
            select(CustomerOwnership).where(CustomerOwnership.source_deal_id == deal.id)
        )).scalar_one()
        await db.refresh(own)
        row = await reload(db, deal.id)
        assert own.valid_until == row.exclusivity_end

    async def test_an_admin_can_grant_less_than_was_asked(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        original_end = deal.exclusivity_end

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 90},
        )
        r = await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager),
            json={"approve": True, "granted_days": 14, "note": "Two weeks only"},
        )
        assert r.json()["granted_days"] == 14
        row = await reload(db, deal.id)
        assert row.exclusivity_end == original_end + timedelta(days=14)

    async def test_refusing_leaves_the_window_alone(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        original_end = deal.exclusivity_end

        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        r = await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager),
            json={"approve": False, "note": "Another partner is closer"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "refused"
        assert (await reload(db, deal.id)).exclusivity_end == original_end

    async def test_the_partner_is_told_either_way(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.manager), json={"approve": False},
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        assert any(
            n["type"] == "exclusivity_extension_refused" for n in notes.json()["items"]
        )

    async def test_a_decided_request_cannot_be_decided_again(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        req_id = created.json()["id"]
        await client.post(
            f"/api/v1/dashboard/deals/extensions/{req_id}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )
        again = await client.post(
            f"/api/v1/dashboard/deals/extensions/{req_id}/decide",
            headers=auth_header(w.manager), json={"approve": True},
        )
        assert again.status_code == 409
        assert again.json()["code"] == "EXTENSION_ALREADY_DECIDED"

    async def test_a_partner_cannot_decide_their_own_request(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        r = await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.partner), json={"approve": True},
        )
        assert r.status_code in (403, 404)

    async def test_an_out_of_scope_admin_cannot_decide(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        created = await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        r = await client.post(
            f"/api/v1/dashboard/deals/extensions/{created.json()['id']}/decide",
            headers=auth_header(w.other_admin), json={"approve": True},
        )
        assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# The queues
# ---------------------------------------------------------------------------

class TestQueues:
    pytestmark = asyncio_test

    async def test_expiring_lists_only_windows_inside_the_warning_period(self, client, db):
        w = await build(db)
        soon = await approved_deal(db, w, ends_in_days=3)
        later = await approved_deal(db, w, ends_in_days=120)

        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.partner)
        )
        assert r.status_code == 200, r.text[:300]
        ids = {row["deal_id"] for row in r.json()}
        assert soon.id in ids
        assert later.id not in ids

    async def test_expiring_reports_the_days_left(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=4)
        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.partner)
        )
        row = next(x for x in r.json() if x["deal_id"] == deal.id)
        assert row["days_left"] == 4

    async def test_a_partner_sees_only_their_own(self, client, db):
        w = await build(db)
        mine = await approved_deal(db, w, ends_in_days=3)

        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.other_partner)
        )
        assert mine.id not in {row["deal_id"] for row in r.json()}

    async def test_an_out_of_scope_admin_sees_nothing_of_it(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=3)
        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.other_admin)
        )
        assert deal.id not in {row["deal_id"] for row in r.json()}

    async def test_a_superadmin_sees_every_company(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=3)
        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.superadmin)
        )
        assert deal.id in {row["deal_id"] for row in r.json()}

    async def test_expiring_flags_a_request_already_waiting(self, client, db):
        # So the UI offers "request an extension" only where it would be taken.
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=3)
        await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )
        r = await client.get(
            "/api/v1/dashboard/deals/expiring", headers=auth_header(w.partner)
        )
        row = next(x for x in r.json() if x["deal_id"] == deal.id)
        assert row["extension_pending"] is True

    async def test_the_request_list_is_scoped(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=5)
        await client.post(
            f"/api/v1/dashboard/deals/{deal.id}/extension",
            headers=auth_header(w.partner), json={"days": 30},
        )

        mine = await client.get(
            "/api/v1/dashboard/deals/extensions", headers=auth_header(w.partner)
        )
        assert deal.id in {r["deal_id"] for r in mine.json()}

        theirs = await client.get(
            "/api/v1/dashboard/deals/extensions", headers=auth_header(w.other_partner)
        )
        assert deal.id not in {r["deal_id"] for r in theirs.json()}

        out_of_book = await client.get(
            "/api/v1/dashboard/deals/extensions", headers=auth_header(w.other_admin)
        )
        assert deal.id not in {r["deal_id"] for r in out_of_book.json()}

    async def test_a_sales_rep_is_kept_out(self, client, db):
        w = await build(db)
        rep = await make_user(db, role=UserRole.SALES_REP)
        await db.commit()
        for path in ("/api/v1/dashboard/deals/expiring", "/api/v1/dashboard/deals/extensions"):
            r = await client.get(path, headers=auth_header(rep))
            assert r.status_code in (403, 404), path

    async def test_the_deal_list_carries_the_days_left(self, client, db):
        w = await build(db)
        deal = await approved_deal(db, w, ends_in_days=7)
        r = await client.get(
            f"/api/v1/dashboard/deals?company_id={w.company.id}",
            headers=auth_header(w.partner),
        )
        assert r.status_code == 200, r.text[:300]
        row = next(x for x in r.json()["items"] if x["id"] == deal.id)
        assert row["days_left"] == 7
        assert row["extension_pending"] is False
