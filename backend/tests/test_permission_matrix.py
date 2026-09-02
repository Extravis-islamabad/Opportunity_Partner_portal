"""The permission and scoping matrix.

This is the file that should break first when someone widens a scope by
accident. It drives the real app over HTTP and asks, systematically, whether
each role can reach each other role's data.

The world is two rival partner companies, each with its own channel manager,
its own partner users, its own sales rep, and its own opportunity / POC / deal
/ document request. Almost every test is then some form of "A tries to touch
B's thing", which is the shape nearly every real scoping bug takes.

Two conventions worth knowing:

  - The world is built once and reused. Every test is read-only against it, or
    writes something new rather than mutating what others assert on, so they
    stay order-independent without paying to rebuild ~30 rows per test.

  - Assertions on denial accept 403 *or* 404, because some routes deliberately
    answer "not found" rather than confirm a record exists to someone who may
    not see it (commissions do this). What is never acceptable is 2xx.
"""
import pytest

from app.models.company import CompanyType
from app.models.opportunity import OpportunityStatus
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_deal,
    make_doc_request,
    make_opp_document,
    make_opportunity,
    make_poc,
    make_user,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.asyncio]

# A denial. Some routes 404 rather than confirm the record exists to someone
# who should not see it; both are correct, a 2xx never is.
DENIED = {403, 404}


class World:
    """Plain ids and emails — no ORM objects, so it survives the per-test
    engine disposal that keeps asyncpg connections on their own event loop."""


_WORLD: World | None = None


async def _build(db) -> World:
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.manager_a = await make_user(db, role=UserRole.ADMIN)
    w.manager_b = await make_user(db, role=UserRole.ADMIN)

    w.company_a = await make_company(db, channel_manager_id=w.manager_a.id)
    w.company_b = await make_company(db, channel_manager_id=w.manager_b.id)
    w.customer_co = await make_company(
        db, channel_manager_id=w.manager_a.id, company_type=CompanyType.CUSTOMER
    )

    w.partner_a = await make_user(db, role=UserRole.PARTNER, company_id=w.company_a.id)
    w.colleague_a = await make_user(db, role=UserRole.PARTNER, company_id=w.company_a.id)
    w.partner_b = await make_user(db, role=UserRole.PARTNER, company_id=w.company_b.id)
    w.customer_user = await make_user(
        db, role=UserRole.PARTNER, company_id=w.customer_co.id
    )

    w.rep_a = await make_user(db, role=UserRole.SALES_REP)
    w.rep_b = await make_user(db, role=UserRole.SALES_REP)

    w.opp_a = await make_opportunity(
        db, company_id=w.company_a.id, submitted_by=w.partner_a.id,
        status=OpportunityStatus.APPROVED,
    )
    w.opp_a.sales_rep_id = w.rep_a.id
    w.opp_b = await make_opportunity(
        db, company_id=w.company_b.id, submitted_by=w.partner_b.id,
        status=OpportunityStatus.APPROVED,
    )
    w.opp_b.sales_rep_id = w.rep_b.id
    await db.flush()

    w.poc_a = await make_poc(db, opportunity_id=w.opp_a.id)
    w.poc_b = await make_poc(db, opportunity_id=w.opp_b.id)
    w.doc_a = await make_opp_document(db, opportunity_id=w.opp_a.id)
    w.doc_b = await make_opp_document(db, opportunity_id=w.opp_b.id)
    w.deal_a = await make_deal(
        db, company_id=w.company_a.id, registered_by=w.partner_a.id
    )
    w.deal_b = await make_deal(
        db, company_id=w.company_b.id, registered_by=w.partner_b.id
    )
    w.docreq_a = await make_doc_request(
        db, company_id=w.company_a.id, requested_by=w.partner_a.id
    )
    w.docreq_b = await make_doc_request(
        db, company_id=w.company_b.id, requested_by=w.partner_b.id
    )
    await db.commit()

    # Flatten to primitives: ORM instances must not outlive this session, and
    # the world is reused across tests that each get a fresh one.
    return _flatten(w)


def _flatten(w) -> World:
    flat = World()
    for name, value in vars(w).items():
        setattr(flat, name, value.id)
        if hasattr(value, "email"):
            setattr(flat, f"{name}_email", value.email)
            setattr(flat, f"{name}_name", value.full_name)
    return flat



async def _throwaway_opportunity(db, w) -> int:
    """A fresh opportunity in company B, for tests that attempt a mutation.

    Destructive attempts must not aim at the shared world: if the mutation
    unexpectedly succeeds, every later test loses the row it asserts on and
    the real failure is buried under a cascade of unrelated ones.
    """
    opp = await make_opportunity(
        db, company_id=w.company_b, submitted_by=w.partner_b,
        status=OpportunityStatus.PENDING_REVIEW,
    )
    await db.commit()
    return opp.id


@pytest.fixture
def actors():
    """Auth headers by role name, minted from the ids in the shared world."""
    def _for(user_id: int, role: UserRole, company_id: int | None = None):
        from types import SimpleNamespace

        return auth_header(
            SimpleNamespace(id=user_id, role=role, company_id=company_id)
        )
    return _for


@pytest.fixture
async def w(db):
    global _WORLD
    if _WORLD is None:
        _WORLD = await _build(db)
    return _WORLD


@pytest.fixture
def hdr(w, actors):
    """Every actor's Authorization header, ready to use."""
    return {
        "superadmin": actors(w.superadmin, UserRole.ADMIN),
        "manager_a": actors(w.manager_a, UserRole.ADMIN),
        "manager_b": actors(w.manager_b, UserRole.ADMIN),
        "partner_a": actors(w.partner_a, UserRole.PARTNER, w.company_a),
        "colleague_a": actors(w.colleague_a, UserRole.PARTNER, w.company_a),
        "partner_b": actors(w.partner_b, UserRole.PARTNER, w.company_b),
        "customer_user": actors(w.customer_user, UserRole.PARTNER, w.customer_co),
        "rep_a": actors(w.rep_a, UserRole.SALES_REP),
        "rep_b": actors(w.rep_b, UserRole.SALES_REP),
    }


# ---------------------------------------------------------------------------
# Authentication itself
# ---------------------------------------------------------------------------

class TestUnauthenticated:
    @pytest.mark.parametrize("path", [
        "/api/v1/opportunities",
        "/api/v1/companies",
        "/api/v1/users",
        "/api/v1/dashboard/deals",
        "/api/v1/commissions",
        "/api/v1/pocs",
        "/api/v1/audit-logs",
        "/api/v1/exports/opportunities.xlsx",
    ])
    async def test_no_token_is_refused(self, client, path):
        assert (await client.get(path)).status_code == 401

    @pytest.mark.parametrize("header", [
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
    ])
    async def test_a_broken_token_is_refused(self, client, header):
        r = await client.get("/api/v1/opportunities", headers=header)
        assert r.status_code == 401

    async def test_a_token_for_a_deleted_user_is_refused(self, client, db, actors):
        ghost = await make_user(db, role=UserRole.PARTNER)
        from datetime import datetime, timezone

        ghost.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        r = await client.get(
            "/api/v1/auth/me", headers=actors(ghost.id, UserRole.PARTNER)
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Partner → another partner's data
# ---------------------------------------------------------------------------

class TestPartnerAgainstRivalPartner:
    async def test_cannot_read_the_rival_opportunity(self, client, w, hdr):
        r = await client.get(f"/api/v1/opportunities/{w.opp_b}", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_rival_opportunity_absent_from_the_list(self, client, w, hdr):
        r = await client.get("/api/v1/opportunities?page_size=100", headers=hdr["partner_a"])
        assert r.status_code == 200
        ids = {i["id"] for i in r.json()["items"]}
        assert w.opp_a in ids
        assert w.opp_b not in ids

    async def test_company_id_filter_cannot_escape_the_scope(self, client, w, hdr):
        r = await client.get(
            f"/api/v1/opportunities?company_id={w.company_b}", headers=hdr["partner_a"]
        )
        assert r.status_code == 200
        assert r.json()["items"] == []

    @pytest.mark.parametrize("method,suffix,body", [
        ("put", "", {"name": "hijacked"}),
        ("post", "/submit", None),
        ("post", "/approve", {}),
        ("post", "/reject", {"rejection_reason": "no"}),
        ("post", "/notes", {"internal_notes": "x"}),
        ("delete", "", None),
    ])
    async def test_cannot_write_to_the_rival_opportunity(
        self, client, w, hdr, method, suffix, body
    ):
        r = await getattr(client, method)(
            f"/api/v1/opportunities/{w.opp_b}{suffix}",
            headers=hdr["partner_a"],
            **({"json": body} if body is not None else {}),
        )
        assert r.status_code in DENIED

    async def test_cannot_read_the_rival_poc(self, client, w, hdr):
        r = await client.get(f"/api/v1/pocs/{w.poc_b}", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_cannot_read_the_rival_doc_request(self, client, w, hdr):
        r = await client.get(
            f"/api/v1/doc-requests/{w.docreq_b}", headers=hdr["partner_a"]
        )
        assert r.status_code in DENIED

    async def test_cannot_read_the_rival_scorecard(self, client, w, hdr):
        r = await client.get(f"/api/v1/scorecard/{w.company_b}", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_cannot_read_the_rival_company_performance(self, client, w, hdr):
        r = await client.get(
            f"/api/v1/dashboard/company/{w.company_b}/performance",
            headers=hdr["partner_a"],
        )
        assert r.status_code in DENIED

    async def test_rival_deals_absent_from_the_deal_list(self, client, w, hdr):
        r = await client.get("/api/v1/dashboard/deals?page_size=100", headers=hdr["partner_a"])
        assert r.status_code == 200
        ids = {d["id"] for d in r.json()["items"]}
        assert w.deal_a in ids
        assert w.deal_b not in ids

    async def test_rival_doc_requests_absent_from_the_list(self, client, w, hdr):
        r = await client.get("/api/v1/doc-requests?page_size=100", headers=hdr["partner_a"])
        assert r.status_code == 200
        ids = {d["id"] for d in r.json()["items"]}
        assert w.docreq_a in ids
        assert w.docreq_b not in ids

    async def test_rival_rows_absent_from_the_export(self, client, w, hdr):
        # An export that ignores scope hands over exactly the rows the UI
        # refuses to show.
        r = await client.get("/api/v1/exports/opportunities.xlsx", headers=hdr["partner_a"])
        assert r.status_code == 200
        from io import BytesIO

        from openpyxl import load_workbook

        ws = load_workbook(BytesIO(r.content)).active
        names = {str(c.value) for row in ws.iter_rows(min_row=2) for c in row if c.value}
        assert not any(str(w.opp_b) == n for n in names)

    async def test_cannot_enumerate_a_rival_user(self, client, w, hdr):
        r = await client.get(f"/api/v1/users/{w.partner_b}", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_cannot_list_users(self, client, w, hdr):
        r = await client.get("/api/v1/users", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_cannot_list_companies(self, client, w, hdr):
        r = await client.get("/api/v1/companies", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_cannot_read_the_audit_log(self, client, w, hdr):
        r = await client.get("/api/v1/audit-logs", headers=hdr["partner_a"])
        assert r.status_code in DENIED


# ---------------------------------------------------------------------------
# Partner → their own colleague (reads widened, writes did not)
# ---------------------------------------------------------------------------

class TestPartnerAgainstColleague:
    async def test_colleague_can_read_the_opportunity(self, client, w, hdr):
        r = await client.get(f"/api/v1/opportunities/{w.opp_a}", headers=hdr["colleague_a"])
        assert r.status_code == 200

    @pytest.mark.parametrize("method,suffix,body", [
        ("put", "", {"name": "renamed by a colleague"}),
        ("post", "/submit", None),
    ])
    async def test_colleague_cannot_write_the_opportunity(
        self, client, w, hdr, method, suffix, body
    ):
        r = await getattr(client, method)(
            f"/api/v1/opportunities/{w.opp_a}{suffix}",
            headers=hdr["colleague_a"],
            **({"json": body} if body is not None else {}),
        )
        assert r.status_code in DENIED

    async def test_colleague_cannot_touch_the_documents(self, client, w, hdr):
        # The upload hole: this used to have no check at all.
        r = await client.delete(
            f"/api/v1/opportunities/{w.opp_a}/documents/{w.doc_a}",
            headers=hdr["colleague_a"],
        )
        assert r.status_code in DENIED

    async def test_partner_never_sees_internal_notes(self, client, w, hdr):
        r = await client.get(f"/api/v1/opportunities/{w.opp_a}", headers=hdr["partner_a"])
        assert r.status_code == 200
        assert r.json()["internal_notes"] is None


# ---------------------------------------------------------------------------
# Channel manager → outside their book
# ---------------------------------------------------------------------------

class TestChannelManagerOutsideTheirBook:
    async def test_cannot_read_a_company_they_do_not_manage(self, client, w, hdr):
        r = await client.get(f"/api/v1/companies/{w.company_b}", headers=hdr["manager_a"])
        assert r.status_code in DENIED

    async def test_cannot_edit_a_company_they_do_not_manage(self, client, w, hdr):
        # The escalation this guards: setting channel_manager_id to themselves
        # would widen their own scope everywhere else.
        r = await client.put(
            f"/api/v1/companies/{w.company_b}",
            headers=hdr["manager_a"],
            json={"channel_manager_id": w.manager_a},
        )
        assert r.status_code in DENIED

    async def test_cannot_create_a_company(self, client, w, hdr):
        r = await client.post(
            "/api/v1/companies",
            headers=hdr["manager_a"],
            json={
                "name": "Sneaky Co", "country": "US", "region": "NA", "city": "Austin",
                "industry": "Tech", "contact_email": "s@fixture.example.com",
                "channel_manager_id": w.manager_a, "company_type": "partner",
            },
        )
        assert r.status_code in DENIED

    async def test_cannot_delete_a_company(self, client, w, hdr):
        r = await client.delete(f"/api/v1/companies/{w.company_a}", headers=hdr["manager_a"])
        assert r.status_code in DENIED

    async def test_out_of_book_companies_absent_from_the_list(self, client, w, hdr):
        r = await client.get("/api/v1/companies?page_size=100", headers=hdr["manager_a"])
        assert r.status_code == 200
        ids = {c["id"] for c in r.json()["items"]}
        assert w.company_a in ids
        assert w.company_b not in ids

    @pytest.mark.parametrize("suffix,body", [
        ("/approve", {}),
        ("/reject", {"rejection_reason": "no"}),
        ("/notes", {"internal_notes": "x"}),
        ("/review", {}),
    ])
    async def test_cannot_act_on_an_out_of_book_opportunity(
        self, client, w, hdr, db, suffix, body
    ):
        # Its own opportunity, not the shared one: these routes mutate, and a
        # regression here would otherwise corrupt the world for every test
        # that runs after it — which is how this suite first surfaced the bug.
        victim = await _throwaway_opportunity(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{victim}{suffix}", headers=hdr["manager_a"], json=body
        )
        assert r.status_code in DENIED

    async def test_cannot_delete_an_out_of_book_opportunity(self, client, w, hdr, db):
        victim = await _throwaway_opportunity(db, w)
        r = await client.delete(f"/api/v1/opportunities/{victim}", headers=hdr["manager_a"])
        assert r.status_code in DENIED

    async def test_out_of_book_opportunities_absent_from_the_list(self, client, w, hdr):
        r = await client.get("/api/v1/opportunities?page_size=100", headers=hdr["manager_a"])
        ids = {i["id"] for i in r.json()["items"]}
        assert w.opp_a in ids
        assert w.opp_b not in ids

    async def test_cannot_fulfil_an_out_of_book_doc_request(self, client, w, hdr):
        # Found by the upload audit: the GET checked scope, fulfil did not —
        # and fulfil can push the file into the global knowledge base.
        r = await client.post(
            f"/api/v1/doc-requests/{w.docreq_b}/fulfill",
            headers=hdr["manager_a"],
            files={"file": ("x.pdf", b"%PDF-1.4 fixture", "application/pdf")},
        )
        assert r.status_code in DENIED

    async def test_cannot_decline_an_out_of_book_doc_request(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/doc-requests/{w.docreq_b}/decline",
            headers=hdr["manager_a"],
            json={"decline_reason": "no"},
        )
        assert r.status_code in DENIED

    async def test_cannot_upload_to_an_out_of_book_opportunity(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/opportunities/{w.opp_b}/documents",
            headers=hdr["manager_a"],
            files={"file": ("x.pdf", b"%PDF-1.4 fixture", "application/pdf")},
        )
        assert r.status_code in DENIED

    async def test_cannot_manage_a_user_outside_their_book(self, client, w, hdr):
        r = await client.put(
            f"/api/v1/users/{w.partner_b}",
            headers=hdr["manager_a"],
            json={"full_name": "Renamed by a stranger"},
        )
        assert r.status_code in DENIED

    async def test_cannot_deactivate_a_peer_admin(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/users/{w.manager_b}/deactivate", headers=hdr["manager_a"]
        )
        assert r.status_code in DENIED

    async def test_cannot_deactivate_the_superadmin(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/users/{w.superadmin}/deactivate", headers=hdr["manager_a"]
        )
        assert r.status_code in DENIED

    async def test_cannot_read_an_out_of_book_scorecard(self, client, w, hdr):
        r = await client.get(f"/api/v1/scorecard/{w.company_b}", headers=hdr["manager_a"])
        assert r.status_code in DENIED

    async def test_cannot_bulk_import_companies(self, client, w, hdr):
        r = await client.post(
            "/api/v1/companies/bulk-import",
            headers=hdr["manager_a"],
            files={"file": ("c.xlsx", b"not-a-real-xlsx", "application/vnd.ms-excel")},
        )
        assert r.status_code in DENIED

    async def test_out_of_book_rows_absent_from_exports(self, client, w, hdr):
        r = await client.get("/api/v1/exports/companies.xlsx", headers=hdr["manager_a"])
        assert r.status_code == 200
        from io import BytesIO

        from openpyxl import load_workbook

        ws = load_workbook(BytesIO(r.content)).active
        ids = {row[0].value for row in ws.iter_rows(min_row=2) if row[0].value}
        assert w.company_a in ids
        assert w.company_b not in ids


# ---------------------------------------------------------------------------
# Sales rep → everything they are denied
# ---------------------------------------------------------------------------

class TestSalesRepDenials:
    @pytest.mark.parametrize("path", [
        "/api/v1/dashboard/deals",
        "/api/v1/commissions",
        "/api/v1/commissions/statements/list",
        "/api/v1/scorecard/me",
        "/api/v1/scorecard/leaderboard/top",
        "/api/v1/doc-requests",
        "/api/v1/companies",
        "/api/v1/audit-logs",
        "/api/v1/exports/deals.xlsx",
    ])
    async def test_denied_areas(self, client, hdr, path):
        # These handlers predate the sales-rep role and branch "if partner …
        # else assume admin". A rep must be denied explicitly, never fall
        # through into the admin branch and read everything.
        r = await client.get(path, headers=hdr["rep_a"])
        assert r.status_code in DENIED, f"{path} returned {r.status_code}"

    async def test_cannot_read_an_unassigned_opportunity(self, client, w, hdr):
        r = await client.get(f"/api/v1/opportunities/{w.opp_b}", headers=hdr["rep_a"])
        assert r.status_code in DENIED

    async def test_can_read_their_own_assigned_opportunity(self, client, w, hdr):
        r = await client.get(f"/api/v1/opportunities/{w.opp_a}", headers=hdr["rep_a"])
        assert r.status_code == 200

    async def test_unassigned_opportunities_absent_from_the_list(self, client, w, hdr):
        r = await client.get("/api/v1/opportunities?page_size=100", headers=hdr["rep_a"])
        ids = {i["id"] for i in r.json()["items"]}
        assert w.opp_a in ids
        assert w.opp_b not in ids

    async def test_cannot_read_an_unassigned_poc(self, client, w, hdr):
        r = await client.get(f"/api/v1/pocs/{w.poc_b}", headers=hdr["rep_a"])
        assert r.status_code in DENIED

    @pytest.mark.parametrize("suffix,body", [
        ("", {"notes": "hijacked"}),
        ("/close", {"successful": True}),
        ("/reopen", None),
    ])
    async def test_cannot_write_an_unassigned_poc(self, client, w, hdr, suffix, body):
        method = client.put if suffix == "" else client.post
        r = await method(
            f"/api/v1/pocs/{w.poc_b}{suffix}",
            headers=hdr["rep_a"],
            **({"json": body} if body is not None else {}),
        )
        assert r.status_code in DENIED

    async def test_cannot_touch_documents_on_an_unassigned_opportunity(
        self, client, w, hdr
    ):
        # Upload had no check at all; delete checked only the partner branch,
        # so a rep fell straight through it.
        upload = await client.post(
            f"/api/v1/opportunities/{w.opp_b}/documents",
            headers=hdr["rep_a"],
            files={"file": ("x.pdf", b"%PDF-1.4 fixture", "application/pdf")},
        )
        assert upload.status_code in DENIED

        delete = await client.delete(
            f"/api/v1/opportunities/{w.opp_b}/documents/{w.doc_b}",
            headers=hdr["rep_a"],
        )
        assert delete.status_code in DENIED

    async def test_cannot_read_another_reps_activity_log(self, client, w, hdr):
        r = await client.get(
            f"/api/v1/activities/month?month=2026-08&user_id={w.rep_b}",
            headers=hdr["rep_a"],
        )
        assert r.status_code in DENIED

    async def test_cannot_approve_an_opportunity(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/opportunities/{w.opp_a}/approve", headers=hdr["rep_a"], json={}
        )
        assert r.status_code in DENIED

    async def test_cannot_create_an_opportunity_without_naming_a_partner(
        self, client, w, hdr
    ):
        # A rep may register on a partner's behalf (tests/test_sales_rep_
        # registration.py) — but the lock has to belong to somebody, and the
        # service refuses to guess who. No company means no registration.
        r = await client.post(
            "/api/v1/opportunities",
            headers=hdr["rep_a"],
            json={
                "name": "x", "customer_name": "y", "region": "NA", "country": "US",
                "city": "Austin", "worth": 1000, "closing_date": "2027-01-01",
                "requirements": "r",
            },
        )
        assert r.status_code == 400
        assert r.json()["code"] == "PARTNER_REQUIRED"

    async def test_cannot_register_for_a_customer_company(self, client, w, hdr):
        # A customer company holds no lock, whoever is typing.
        r = await client.post(
            "/api/v1/opportunities",
            headers=hdr["rep_a"],
            json={
                "name": "x", "customer_name": "y", "region": "NA", "country": "US",
                "city": "Austin", "worth": 1000, "closing_date": "2027-01-01",
                "requirements": "r", "company_id": w.customer_co,
            },
        )
        assert r.status_code == 400
        assert r.json()["code"] == "NOT_A_CHANNEL_PARTNER"


# ---------------------------------------------------------------------------
# Role confusion: each role reaching for another's routes
# ---------------------------------------------------------------------------

class TestRoleConfusion:
    async def test_partner_cannot_reach_admin_analytics(self, client, hdr):
        r = await client.get("/api/v1/dashboard/admin/stats", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_partner_cannot_approve_a_deal(self, client, w, hdr):
        r = await client.post(
            f"/api/v1/dashboard/deals/{w.deal_a}/approve", headers=hdr["partner_a"], json={}
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_upload_to_the_knowledge_base(self, client, hdr):
        r = await client.post(
            "/api/v1/knowledge-base/documents",
            headers=hdr["partner_a"],
            data={"title": "t", "category": "general"},
            files={"file": ("x.pdf", b"%PDF-1.4 fixture", "application/pdf")},
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_create_a_user(self, client, w, hdr):
        r = await client.post(
            "/api/v1/users",
            headers=hdr["partner_a"],
            json={
                "full_name": "Mine", "email": "mine@fixture.example.com",
                "role": "admin", "company_id": w.company_a,
            },
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_log_a_sales_activity(self, client, hdr):
        r = await client.post(
            "/api/v1/activities",
            headers=hdr["partner_a"],
            json={"activity_date": "2026-08-20", "activity_type": "call"},
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_read_an_activity_log(self, client, hdr):
        r = await client.get("/api/v1/activities/month?month=2026-08", headers=hdr["partner_a"])
        assert r.status_code in DENIED

    async def test_admin_cannot_use_partner_write_routes(self, client, w, hdr):
        r = await client.put(
            f"/api/v1/opportunities/{w.opp_a}",
            headers=hdr["manager_a"],
            json={"name": "admin edit"},
        )
        assert r.status_code in DENIED

    async def test_admin_cannot_register_an_opportunity(self, client, w, hdr):
        # Raising a registration and approving it are different jobs. The
        # route opened up to sales reps; it must not have opened to the
        # people who review what comes through it.
        r = await client.post(
            "/api/v1/opportunities",
            headers=hdr["superadmin"],
            json={
                "name": "x", "customer_name": "y", "region": "NA", "country": "US",
                "city": "Austin", "worth": 1000, "closing_date": "2027-01-01",
                "requirements": "r", "company_id": w.company_a,
            },
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_register_for_another_company(self, client, w, hdr):
        # The company field exists for reps. A partner naming somebody else's
        # company is refused, not quietly corrected to their own.
        r = await client.post(
            "/api/v1/opportunities",
            headers=hdr["partner_a"],
            json={
                "name": "x", "customer_name": "y", "region": "NA", "country": "US",
                "city": "Austin", "worth": 1000, "closing_date": "2027-01-01",
                "requirements": "r", "company_id": w.company_b,
            },
        )
        assert r.status_code in DENIED

    async def test_partner_cannot_browse_the_partner_or_customer_lists(
        self, client, hdr
    ):
        # Both pickers span every partner's book; they are for Extravis staff.
        for path in ("/api/v1/opportunities/partner-companies",
                     "/api/v1/opportunities/known-customers"):
            r = await client.get(path, headers=hdr["partner_a"])
            assert r.status_code in DENIED, f"{path} returned {r.status_code}"

    async def test_admin_cannot_register_a_deal(self, client, hdr):
        r = await client.post(
            "/api/v1/dashboard/deals",
            headers=hdr["manager_a"],
            json={
                "customer_name": "x", "deal_description": "y",
                "estimated_value": 1000, "expected_close_date": "2027-01-01",
            },
        )
        assert r.status_code in DENIED


# ---------------------------------------------------------------------------
# Customer companies are outside the partner programme entirely
# ---------------------------------------------------------------------------

class TestCustomerCompanyDenials:
    @pytest.mark.parametrize("path", [
        "/api/v1/dashboard/deals",
        "/api/v1/commissions",
        "/api/v1/scorecard/me",
        "/api/v1/scorecard/leaderboard/top",
        "/api/v1/exports/deals.xlsx",
    ])
    async def test_partner_programme_is_unreachable(self, client, hdr, path):
        r = await client.get(path, headers=hdr["customer_user"])
        assert r.status_code in DENIED, f"{path} returned {r.status_code}"

    async def test_cannot_register_a_deal(self, client, hdr):
        r = await client.post(
            "/api/v1/dashboard/deals",
            headers=hdr["customer_user"],
            json={
                "customer_name": "x", "deal_description": "y",
                "estimated_value": 1000, "expected_close_date": "2027-01-01",
            },
        )
        assert r.status_code in DENIED

    async def test_still_reads_its_own_pipeline(self, client, hdr):
        # A customer is outside the programme, not outside the portal.
        r = await client.get("/api/v1/opportunities", headers=hdr["customer_user"])
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Superadmin: the control. If these fail, the tests above prove nothing.
# ---------------------------------------------------------------------------

class TestSuperadminReach:
    @pytest.mark.parametrize("path_attr", [
        "/api/v1/opportunities/{opp_b}",
        "/api/v1/companies/{company_b}",
        "/api/v1/pocs/{poc_b}",
        "/api/v1/doc-requests/{docreq_b}",
        "/api/v1/scorecard/{company_b}",
        "/api/v1/users/{partner_b}",
    ])
    async def test_superadmin_reaches_everything(self, client, w, hdr, path_attr):
        path = path_attr.format(**{k: v for k, v in vars(w).items()})
        r = await client.get(path, headers=hdr["superadmin"])
        assert r.status_code == 200, f"{path} returned {r.status_code}"

    async def test_superadmin_sees_both_companies(self, client, w, hdr):
        r = await client.get("/api/v1/companies?page_size=100", headers=hdr["superadmin"])
        ids = {c["id"] for c in r.json()["items"]}
        assert {w.company_a, w.company_b} <= ids

    async def test_superadmin_sees_both_opportunities(self, client, w, hdr):
        r = await client.get("/api/v1/opportunities?page_size=100", headers=hdr["superadmin"])
        ids = {i["id"] for i in r.json()["items"]}
        assert {w.opp_a, w.opp_b} <= ids
