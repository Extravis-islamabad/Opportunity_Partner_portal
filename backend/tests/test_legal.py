"""The partner agreement and the NDA.

Onboarding used to record that somebody ticked a box. These tests are about
the question that replaced it: is this person's acceptance of the *current*
version on file — and what happens when a new version is published.
"""
import pytest
from sqlalchemy import select

from app.models.company import CompanyType
from app.models.legal import LegalAcceptance, LegalDocument, LegalDocumentKind
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
    w.rep = await make_user(db, role=UserRole.SALES_REP)

    w.customer_company = await make_company(
        db, channel_manager_id=w.manager.id, company_type=CompanyType.CUSTOMER
    )
    w.customer_user = await make_user(
        db, role=UserRole.PARTNER, company_id=w.customer_company.id
    )
    await db.commit()
    return w


async def publish(client, w, *, kind="partner_agreement", version=None, title=None):
    version = version or unique("v")
    r = await client.post(
        "/api/v1/legal/documents",
        headers=auth_header(w.superadmin),
        json={
            "kind": kind,
            "version": version,
            "title": title or "Extravis Partner Agreement",
            "body": "You agree to the terms of the Extravis partner programme.",
        },
    )
    assert r.status_code == 201, r.text[:300]
    return r.json()


def _opportunity_payload():
    return {
        "name": "Legal gate deal",
        "customer_name": unique("Meridian"),
        "region": "NA",
        "country": "US",
        "city": "Austin",
        "worth": 50000,
        "closing_date": "2027-06-30",
        "requirements": "Rollout.",
        "status": "draft",
    }


class TestPublishing:
    pytestmark = asyncio_test

    async def test_a_superadmin_can_publish(self, client, db):
        w = await build(db)
        body = await publish(client, w)
        assert body["kind"] == "partner_agreement"

    async def test_a_channel_manager_cannot(self, client, db):
        # Publishing asks every partner in the programme to agree again.
        w = await build(db)
        r = await client.post(
            "/api/v1/legal/documents",
            headers=auth_header(w.manager),
            json={
                "kind": "nda", "version": "x", "title": "T", "body": "B",
            },
        )
        assert r.status_code in (403, 404)

    async def test_a_partner_cannot(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/legal/documents",
            headers=auth_header(w.partner),
            json={"kind": "nda", "version": "x", "title": "T", "body": "B"},
        )
        assert r.status_code in (403, 404)

    async def test_the_same_version_cannot_be_published_twice(self, client, db):
        # Editing a version somebody accepted would make their acceptance a
        # record of text that never existed.
        w = await build(db)
        version = unique("v")
        await publish(client, w, version=version)
        r = await client.post(
            "/api/v1/legal/documents",
            headers=auth_header(w.superadmin),
            json={
                "kind": "partner_agreement", "version": version,
                "title": "Rewritten", "body": "Different terms",
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "VERSION_EXISTS"

    async def test_an_invented_kind_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/legal/documents",
            headers=auth_header(w.superadmin),
            json={"kind": "loyalty_oath", "version": "1", "title": "T", "body": "B"},
        )
        assert r.status_code == 422


class TestPending:
    pytestmark = asyncio_test

    async def test_nothing_published_asks_nothing(self, client, db):
        # A portal with no agreement loaded must not block every partner in it.
        w = await build(db)
        r = await client.get("/api/v1/legal/pending", headers=auth_header(w.partner))
        assert r.status_code == 200, r.text[:300]
        # Other tests may have published; what matters is the endpoint answers.
        assert isinstance(r.json(), list)

    async def test_a_published_document_is_pending_for_a_partner(self, client, db):
        w = await build(db)
        doc = await publish(client, w)
        r = await client.get("/api/v1/legal/pending", headers=auth_header(w.partner))
        assert doc["id"] in {d["id"] for d in r.json()}

    async def test_accepting_clears_it(self, client, db):
        w = await build(db)
        doc = await publish(client, w)
        accepted = await client.post(
            f"/api/v1/legal/{doc['id']}/accept", headers=auth_header(w.partner)
        )
        assert accepted.status_code == 201, accepted.text[:300]

        r = await client.get("/api/v1/legal/pending", headers=auth_header(w.partner))
        assert doc["id"] not in {d["id"] for d in r.json()}

    async def test_a_new_version_asks_again(self, client, db):
        # The point of versioning: what they agreed to is no longer in force.
        w = await build(db)
        first = await publish(client, w)
        await client.post(
            f"/api/v1/legal/{first['id']}/accept", headers=auth_header(w.partner)
        )
        assert first["id"] not in {
            d["id"] for d in
            (await client.get("/api/v1/legal/pending", headers=auth_header(w.partner))).json()
        }

        second = await publish(client, w)
        pending = await client.get(
            "/api/v1/legal/pending", headers=auth_header(w.partner)
        )
        assert second["id"] in {d["id"] for d in pending.json()}

    async def test_the_old_acceptance_is_kept(self, client, db):
        # It is the record of what was agreed and when, not a stale row.
        w = await build(db)
        first = await publish(client, w)
        await client.post(
            f"/api/v1/legal/{first['id']}/accept", headers=auth_header(w.partner)
        )
        await publish(client, w)

        history = await client.get(
            "/api/v1/legal/my-acceptances", headers=auth_header(w.partner)
        )
        assert first["version"] in {a["version"] for a in history.json()}

    async def test_accepting_twice_is_not_a_second_agreement(self, client, db):
        w = await build(db)
        doc = await publish(client, w)
        headers = auth_header(w.partner)
        first = await client.post(f"/api/v1/legal/{doc['id']}/accept", headers=headers)
        second = await client.post(f"/api/v1/legal/{doc['id']}/accept", headers=headers)
        assert second.status_code == 201, second.text[:300]
        assert first.json()["id"] == second.json()["id"]

        rows = (await db.execute(
            select(LegalAcceptance).where(
                LegalAcceptance.user_id == w.partner.id,
                LegalAcceptance.document_id == doc["id"],
            )
        )).scalars().all()
        assert len(rows) == 1

    async def test_staff_are_not_asked(self, client, db):
        # They are covered by employment, not a partner agreement.
        w = await build(db)
        await publish(client, w)
        for actor in (w.manager, w.rep, w.superadmin):
            r = await client.get("/api/v1/legal/pending", headers=auth_header(actor))
            assert r.json() == [], actor.role

    async def test_staff_are_not_asked_even_if_attached_to_a_company(
        self, client, db
    ):
        # The role check carries this on its own. Staff normally have no
        # company at all, so the company check would hide a missing role check
        # by accident — this pins the rule rather than the accident.
        from app.services import legal_service

        w = await build(db)
        staff = await make_user(db, role=UserRole.ADMIN, company_id=w.company.id)
        await db.commit()
        await db.refresh(staff, ["company"])

        assert legal_service.applies_to(staff) is False

    async def test_a_customer_company_is_not_asked(self, client, db):
        # A customer is not in the partner programme, so a partner agreement
        # is nonsense they cannot act on.
        w = await build(db)
        await publish(client, w)
        r = await client.get(
            "/api/v1/legal/pending", headers=auth_header(w.customer_user)
        )
        assert r.json() == []

    async def test_both_documents_are_asked_for_separately(self, client, db):
        w = await build(db)
        agreement = await publish(client, w, kind="partner_agreement")
        nda = await publish(client, w, kind="nda", title="Extravis NDA")

        pending = await client.get(
            "/api/v1/legal/pending", headers=auth_header(w.partner)
        )
        ids = {d["id"] for d in pending.json()}
        assert {agreement["id"], nda["id"]} <= ids

        await client.post(
            f"/api/v1/legal/{agreement['id']}/accept", headers=auth_header(w.partner)
        )
        still = await client.get(
            "/api/v1/legal/pending", headers=auth_header(w.partner)
        )
        assert nda["id"] in {d["id"] for d in still.json()}


class TestNothingPublished:
    """A portal with no agreement loaded must not block every partner in it.

    Monkeypatched rather than emptied: the documents table is shared with
    every other test in the suite, and deleting from it to prove a branch
    would break them.
    """

    pytestmark = asyncio_test

    async def test_no_documents_means_nothing_pending(self, client, db, monkeypatch):
        from app.services import legal_service

        w = await build(db)
        await publish(client, w)

        async def _none(_db):
            return []

        monkeypatch.setattr(legal_service, "current_documents", _none)
        assert await legal_service.pending_for(db, w.partner) == []

    async def test_no_documents_means_the_gate_is_open(self, client, db, monkeypatch):
        from app.services import legal_service

        w = await build(db)
        await publish(client, w)

        async def _none(_db):
            return []

        monkeypatch.setattr(legal_service, "current_documents", _none)
        # Must not raise.
        await legal_service.assert_accepted(db, w.partner)


class TestGate:
    pytestmark = asyncio_test

    async def test_registering_business_is_blocked_until_accepted(self, client, db):
        w = await build(db)
        await publish(client, w)
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_opportunity_payload(),
        )
        assert r.status_code == 403
        assert r.json()["code"] == "LEGAL_ACCEPTANCE_REQUIRED"

    async def test_the_refusal_names_the_document(self, client, db):
        w = await build(db)
        await publish(client, w, kind="nda", title="Extravis NDA")
        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_opportunity_payload(),
        )
        assert "Non-Disclosure Agreement" in r.json()["message"]

    async def test_accepting_unblocks_it(self, client, db):
        w = await build(db)
        for doc in (
            await publish(client, w, kind="partner_agreement"),
            await publish(client, w, kind="nda"),
        ):
            await client.post(
                f"/api/v1/legal/{doc['id']}/accept", headers=auth_header(w.partner)
            )

        r = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner),
            json=_opportunity_payload(),
        )
        assert r.status_code == 201, r.text[:300]

    async def test_deal_registration_is_gated_too(self, client, db):
        w = await build(db)
        await publish(client, w)
        r = await client.post(
            "/api/v1/dashboard/deals",
            headers=auth_header(w.partner),
            json={
                "customer_name": unique("Gated"),
                "deal_description": "Rollout",
                "estimated_value": 1000,
                "expected_close_date": "2027-06-30",
            },
        )
        assert r.status_code == 403
        assert r.json()["code"] == "LEGAL_ACCEPTANCE_REQUIRED"

    async def test_reading_is_not_blocked(self, client, db):
        # Locking someone out of the portal would leave them unable to reach
        # the documents they are being asked to accept.
        w = await build(db)
        await publish(client, w)
        for path in ("/api/v1/opportunities", "/api/v1/dashboard/partner/stats",
                     "/api/v1/legal/pending"):
            r = await client.get(path, headers=auth_header(w.partner))
            assert r.status_code == 200, path

    async def test_a_new_version_blocks_again(self, client, db):
        # The consequence that makes versioning worth anything.
        w = await build(db)
        for doc in (
            await publish(client, w, kind="partner_agreement"),
            await publish(client, w, kind="nda"),
        ):
            await client.post(
                f"/api/v1/legal/{doc['id']}/accept", headers=auth_header(w.partner)
            )
        allowed = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner), json=_opportunity_payload(),
        )
        assert allowed.status_code == 201

        await publish(client, w, kind="partner_agreement")
        blocked = await client.post(
            "/api/v1/opportunities",
            headers=auth_header(w.partner), json=_opportunity_payload(),
        )
        assert blocked.status_code == 403


class TestEvidence:
    pytestmark = asyncio_test

    async def test_an_acceptance_records_when_and_from_where(self, client, db):
        w = await build(db)
        doc = await publish(client, w)
        await client.post(
            f"/api/v1/legal/{doc['id']}/accept", headers=auth_header(w.partner)
        )
        row = (await db.execute(
            select(LegalAcceptance).where(
                LegalAcceptance.user_id == w.partner.id,
                LegalAcceptance.document_id == doc["id"],
            )
        )).scalar_one()
        assert row.accepted_at is not None
        assert row.user_agent is not None or row.ip_address is not None

    async def test_a_superadmin_can_see_somebody_elses_history(self, client, db):
        w = await build(db)
        doc = await publish(client, w)
        await client.post(
            f"/api/v1/legal/{doc['id']}/accept", headers=auth_header(w.partner)
        )
        r = await client.get(
            f"/api/v1/legal/users/{w.partner.id}/acceptances",
            headers=auth_header(w.superadmin),
        )
        assert r.status_code == 200, r.text[:300]
        assert doc["version"] in {a["version"] for a in r.json()}

    async def test_a_partner_cannot_read_another_persons_history(self, client, db):
        w = await build(db)
        r = await client.get(
            f"/api/v1/legal/users/{w.partner.id}/acceptances",
            headers=auth_header(w.partner),
        )
        assert r.status_code in (403, 404)

    async def test_the_current_document_is_the_latest_published(self, client, db):
        from app.services import legal_service

        w = await build(db)
        await publish(client, w, kind="nda", version=unique("old"))
        newest = await publish(client, w, kind="nda", version=unique("new"))

        current = await legal_service.current_documents(db)
        nda = next(d for d in current if d.kind == LegalDocumentKind.NDA)
        assert nda.id == newest["id"]
