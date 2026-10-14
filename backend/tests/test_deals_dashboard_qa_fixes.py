"""QA fixes in deal registration, exclusivity and the dashboards.

Each test is one reported defect, asserted by its consequence: an
out-of-scope channel manager cannot approve a deal (and so cannot write
customer ownership or commission), a new registration reaches the people who
can decide it and nobody else, and the dashboard counts what is actually there.
"""
from decimal import Decimal

import pytest
from sqlalchemy import insert, select

from app.models.company import company_channel_managers
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.notification import Notification
from app.models.opportunity import OpportunityStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_deal,
    make_opportunity,
    make_user,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.asyncio]

API = "/api/v1/dashboard"


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.manager = await make_user(db, role=UserRole.ADMIN)
    w.co_manager = await make_user(db, role=UserRole.ADMIN)
    w.outsider = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.manager.id)
    await db.execute(insert(company_channel_managers).values(
        company_id=w.company.id, user_id=w.co_manager.id
    ))
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.other_company = await make_company(db, channel_manager_id=w.outsider.id)
    await db.commit()
    return w


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing mail instead of sending it."""
    mails: list[list[str]] = []

    async def _capture(to_emails, **kwargs):
        mails.append(list(to_emails))
        return True

    monkeypatch.setattr(
        "app.services.notification_service.send_template_email", _capture
    )
    return mails


async def notified(db, deal_id, kind) -> set[int]:
    rows = (await db.execute(
        select(Notification.user_id).where(
            Notification.entity_type == "deal_registration",
            Notification.entity_id == deal_id,
            Notification.type == kind,
        )
    )).scalars().all()
    return set(rows)


# ---------------------------------------------------------------------------
# 1. Approve / reject scope
# ---------------------------------------------------------------------------

async def test_out_of_scope_manager_cannot_approve(client, db, sent):
    w = await build(db)
    deal = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    await db.commit()

    r = await client.post(
        f"{API}/deals/{deal.id}/approve", json={"exclusivity_days": 90},
        headers=auth_header(w.outsider),
    )
    assert r.status_code == 403, r.text

    row = (await db.execute(
        select(DealRegistration).where(DealRegistration.id == deal.id)
    )).scalar_one()
    await db.refresh(row)
    assert row.status == DealStatus.PENDING
    assert row.exclusivity_end is None


async def test_out_of_scope_manager_cannot_reject(client, db, sent):
    w = await build(db)
    deal = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    await db.commit()

    r = await client.post(
        f"{API}/deals/{deal.id}/reject", json={"rejection_reason": "no"},
        headers=auth_header(w.outsider),
    )
    assert r.status_code == 403, r.text


async def test_co_manager_and_superadmin_can_decide(client, db, sent):
    w = await build(db)
    a = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    b = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    await db.commit()

    r = await client.post(
        f"{API}/deals/{a.id}/approve", json={"exclusivity_days": 30},
        headers=auth_header(w.co_manager),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    r = await client.post(
        f"{API}/deals/{b.id}/reject", json={"rejection_reason": "dup"},
        headers=auth_header(w.superadmin),
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("days", [100_000_000, 0, -30])
async def test_exclusivity_days_is_bounded(client, db, sent, days):
    w = await build(db)
    deal = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    await db.commit()

    r = await client.post(
        f"{API}/deals/{deal.id}/approve", json={"exclusivity_days": days},
        headers=auth_header(w.manager),
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 2. Who hears about a new registration
# ---------------------------------------------------------------------------

async def test_registration_notifies_managers_and_superadmins_only(client, db, sent):
    w = await build(db)

    r = await client.post(
        f"{API}/deals",
        json={
            "customer_name": "QA Notify Customer " + str(w.company.id),
            "deal_description": "x",
            "estimated_value": "1000",
            "expected_close_date": "2027-06-30",
        },
        headers=auth_header(w.partner),
    )
    assert r.status_code == 201, r.text
    deal_id = r.json()["id"]

    who = await notified(db, deal_id, "deal_registered")
    assert {w.manager.id, w.co_manager.id, w.superadmin.id} <= who
    assert w.outsider.id not in who
    # One email per recipient, never the whole admin list in one message.
    assert all(len(m) == 1 for m in sent)
    assert [w.outsider.email] not in sent


# ---------------------------------------------------------------------------
# 3. Channel-manager dashboard counts
# ---------------------------------------------------------------------------

async def test_channel_manager_dashboard_does_not_fan_out(client, db):
    w = await build(db)
    # A second partner user is what multiplied the counts before.
    await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    for _ in range(3):
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
    await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner.id,
        status=OpportunityStatus.APPROVED,
    )
    await db.commit()

    for admin in (w.manager, w.co_manager):
        r = await client.get(f"{API}/channel-manager", headers=auth_header(admin))
        assert r.status_code == 200, r.text
        rows = {c["company_id"]: c for c in r.json()["companies"]}
        # The co-manager sees the company too, via Company.managed_by.
        assert w.company.id in rows
        row = rows[w.company.id]
        assert row["partner_count"] == 2
        assert row["pending_opportunities"] == 3
        assert row["approved_opportunities"] == 1


# ---------------------------------------------------------------------------
# 4. Company performance scope and 404
# ---------------------------------------------------------------------------

async def test_company_performance_is_scoped(client, db):
    w = await build(db)

    r = await client.get(
        f"{API}/company/{w.company.id}/performance", headers=auth_header(w.outsider)
    )
    assert r.status_code == 403, r.text

    for admin in (w.manager, w.co_manager, w.superadmin):
        r = await client.get(
            f"{API}/company/{w.company.id}/performance", headers=auth_header(admin)
        )
        assert r.status_code == 200, r.text


async def test_company_performance_unknown_company_is_404(client, db):
    w = await build(db)
    r = await client.get(
        f"{API}/company/999999999/performance", headers=auth_header(w.superadmin)
    )
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# 5. Bad filters are a 422, not a 500
# ---------------------------------------------------------------------------

async def test_unknown_deal_status_filter_is_422(client, db):
    w = await build(db)
    r = await client.get(f"{API}/deals?status=bogus", headers=auth_header(w.superadmin))
    assert r.status_code == 422, r.text

    r = await client.get(f"{API}/deals?status=pending", headers=auth_header(w.manager))
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 6. Direct deals (no company) and companies with no region
# ---------------------------------------------------------------------------

async def test_dashboards_survive_direct_deals_and_null_region(client, db):
    from datetime import date

    w = await build(db)
    rep = await make_user(db, role=UserRole.SALES_REP)
    w.company.region = None
    w.company.city = None
    direct = await make_opportunity(
        db, company_id=None, submitted_by=rep.id,
        status=OpportunityStatus.PENDING_REVIEW,
    )
    # Overdue, so it lands in the overdue list that used to inner-join Company.
    direct.closing_date = date(2020, 1, 1)
    direct.worth = Decimal("1234.00")
    await make_opportunity(db, company_id=w.company.id, submitted_by=w.partner.id)
    await db.commit()

    for path in (
        "/admin/stats", "/admin/opportunity-breakdown", "/admin/monthly-data",
        "/admin/analytics", "/admin/target-plan", "/admin/city-funnel",
        "/poc-summary", "/deployment", "/channel-manager",
    ):
        for admin in (w.superadmin, w.manager):
            r = await client.get(API + path, headers=auth_header(admin))
            assert r.status_code == 200, (path, r.status_code, r.text[:300])

    stats = (await client.get(
        f"{API}/admin/stats", headers=auth_header(w.superadmin)
    )).json()
    overdue = {o["id"]: o for o in stats["overdue_opportunities"]}
    if direct.id in overdue:  # list is capped at 10 in a shared database
        assert overdue[direct.id]["company_name"] == "Direct (no partner)"

    analytics = (await client.get(
        f"{API}/admin/analytics", headers=auth_header(w.superadmin)
    )).json()
    regions = {r["region"]: r for r in analytics["regions"]}
    assert "Unspecified" in regions
    assert regions["Direct (no partner)"]["opportunity_count"] >= 1

    # A channel manager's view never includes direct deals.
    scoped = (await client.get(
        f"{API}/admin/analytics", headers=auth_header(w.manager)
    )).json()
    assert "Direct (no partner)" not in {r["region"] for r in scoped["regions"]}


# ---------------------------------------------------------------------------
# Second QA pass: registration input
# ---------------------------------------------------------------------------

def deal_body(**overrides):
    from tests.conftest import unique

    body = {
        "customer_name": unique("QA Cust"),
        "deal_description": "x",
        "estimated_value": "1000",
        "expected_close_date": "2027-06-30",
    }
    body.update(overrides)
    return body


async def test_linked_opportunity_must_exist(client, db, sent):
    w = await build(db)
    r = await client.post(
        f"{API}/deals", json=deal_body(opportunity_id=999999999),
        headers=auth_header(w.partner),
    )
    assert r.status_code == 400, r.text


async def test_linked_opportunity_must_be_own_company(client, db, sent):
    w = await build(db)
    other_partner = await make_user(
        db, role=UserRole.PARTNER, company_id=w.other_company.id
    )
    theirs = await make_opportunity(
        db, company_id=w.other_company.id, submitted_by=other_partner.id
    )
    mine = await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner.id
    )
    await db.commit()

    r = await client.post(
        f"{API}/deals", json=deal_body(opportunity_id=theirs.id),
        headers=auth_header(w.partner),
    )
    assert r.status_code == 400, r.text

    r = await client.post(
        f"{API}/deals", json=deal_body(opportunity_id=mine.id),
        headers=auth_header(w.partner),
    )
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("overrides", [
    {"estimated_value": "-5"},
    {"estimated_value": "0"},
    {"estimated_value": "1e20"},
    {"customer_name": ""},
    {"customer_name": "   "},
    {"deal_description": " "},
])
async def test_registration_input_is_bounded(client, db, sent, overrides):
    w = await build(db)
    r = await client.post(
        f"{API}/deals", json=deal_body(**overrides), headers=auth_header(w.partner)
    )
    assert r.status_code == 422, r.text


async def test_blank_rejection_reason_is_422(client, db, sent):
    w = await build(db)
    deal = await make_deal(db, company_id=w.company.id, registered_by=w.partner.id)
    await db.commit()
    r = await client.post(
        f"{API}/deals/{deal.id}/reject", json={"rejection_reason": "  "},
        headers=auth_header(w.manager),
    )
    assert r.status_code == 422, r.text


async def test_exclusivity_conflict_ignores_whitespace_and_case(client, db, sent):
    from tests.conftest import unique

    w = await build(db)
    rival = await make_user(db, role=UserRole.PARTNER, company_id=w.other_company.id)
    base = unique("qa-admin")
    held = await make_deal(
        db, company_id=w.other_company.id, registered_by=rival.id,
        status=DealStatus.APPROVED, customer=f"{base} Cust",
    )
    from datetime import date, timedelta
    held.exclusivity_start = date.today() - timedelta(days=1)
    held.exclusivity_end = date.today() + timedelta(days=30)
    await db.commit()

    for variant in (f"{base}  Cust", f"  {base.upper()}\tCUST "):
        r = await client.post(
            f"{API}/deals", json=deal_body(customer_name=variant),
            headers=auth_header(w.partner),
        )
        assert r.status_code == 409, (variant, r.text)


async def test_unknown_deal_status_filter_is_422_for_partner(client, db):
    w = await build(db)
    r = await client.get(f"{API}/deals?status=foo", headers=auth_header(w.partner))
    assert r.status_code == 422, r.text
