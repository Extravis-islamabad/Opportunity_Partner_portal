"""Handing work over before an account is switched off.

The assertion that matters: deactivation is refused while the account still
holds live work. Everything else is about the work landing somewhere it can
actually be acted on — a partner's pipeline on an admin account is not a
handover, it is a disappearance.
"""
import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.poc import PocStatus
from app.models.poc_team import PocTeamMember, PocTeamRole
from app.models.user import User, UserRole, UserStatus
from tests.conftest import (
    auth_header,
    make_company,
    make_opportunity,
    make_poc,
    make_team_member,
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
    w.leaver = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    w.colleague = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)

    w.other_company = await make_company(db, channel_manager_id=w.manager.id)
    w.outsider = await make_user(
        db, role=UserRole.PARTNER, company_id=w.other_company.id
    )
    w.rep = await make_user(db, role=UserRole.SALES_REP)
    w.other_rep = await make_user(db, role=UserRole.SALES_REP)
    await db.commit()
    return w


async def _reload(db, model, pk):
    row = (await db.execute(select(model).where(model.id == pk))).scalar_one()
    await db.refresh(row)
    return row


class TestOutstandingWork:
    pytestmark = asyncio_test

    async def test_an_account_with_nothing_open_is_clear(self, client, db):
        w = await build(db)
        r = await client.get(
            f"/api/v1/users/{w.leaver.id}/workload", headers=auth_header(w.manager)
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["total"] == 0

    async def test_live_opportunities_count(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()
        r = await client.get(
            f"/api/v1/users/{w.leaver.id}/workload", headers=auth_header(w.manager)
        )
        assert r.json()["counts"]["opportunities_submitted"] == 1

    async def test_closed_deals_do_not_count(self, client, db):
        # A closed deal keeps its original submitter as a matter of record.
        # Reassigning it would rewrite history rather than hand over a job.
        w = await build(db)
        for status in (OpportunityStatus.WON, OpportunityStatus.LOST):
            await make_opportunity(
                db, company_id=w.company.id, submitted_by=w.leaver.id, status=status,
            )
        await db.commit()
        r = await client.get(
            f"/api/v1/users/{w.leaver.id}/workload", headers=auth_header(w.manager)
        )
        assert r.json()["total"] == 0

    async def test_managed_companies_count(self, client, db):
        w = await build(db)
        r = await client.get(
            f"/api/v1/users/{w.manager.id}/workload",
            headers=auth_header(w.superadmin),
        )
        assert r.json()["counts"]["companies_managed"] >= 2

    async def test_poc_seats_and_stage_ownership_count(self, client, db):
        from app.services import poc_service

        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.colleague.id,
            status=OpportunityStatus.APPROVED,
        )
        poc = await make_poc(db, opportunity_id=opp.id, status=PocStatus.RUNNING)
        await make_team_member(
            db, poc_id=poc.id, user_id=w.rep.id, role=PocTeamRole.QA,
            assigned_by=w.manager.id,
        )
        await db.commit()
        await poc_service.set_stage_owner(db, poc.id, "deployment", w.rep.id, w.manager)
        await db.commit()

        r = await client.get(
            f"/api/v1/users/{w.rep.id}/workload", headers=auth_header(w.superadmin)
        )
        counts = r.json()["counts"]
        assert counts["poc_team_seats"] == 1
        assert counts["poc_stages_owned"] == 1


class TestDeactivationGate:
    pytestmark = asyncio_test

    async def test_deactivation_is_refused_while_work_is_open(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/deactivate",
            headers=auth_header(w.manager),
        )
        assert r.status_code == 409
        assert r.json()["code"] == "HANDOVER_REQUIRED"

        row = await _reload(db, User, w.leaver.id)
        assert row.status == UserStatus.ACTIVE, "the account was switched off anyway"

    async def test_the_refusal_says_what_is_outstanding(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/deactivate",
            headers=auth_header(w.manager),
        )
        assert "opportunities submitted" in r.json()["message"]

    async def test_a_clear_account_deactivates(self, client, db):
        w = await build(db)
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/deactivate",
            headers=auth_header(w.manager),
        )
        assert r.status_code == 200, r.text[:300]
        row = await _reload(db, User, w.leaver.id)
        assert row.status == UserStatus.INACTIVE

    async def test_deactivating_after_handover_works(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        handover = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        assert handover.status_code == 200, handover.text[:300]

        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/deactivate",
            headers=auth_header(w.manager),
        )
        assert r.status_code == 200, r.text[:300]

    async def test_closing_a_company_is_refused_while_a_partner_holds_work(
        self, client, db
    ):
        # Deactivating a company switches off its partners, so the same rule
        # has to hold there or the gate is bypassable by closing the company.
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.delete(
            f"/api/v1/companies/{w.company.id}", headers=auth_header(w.superadmin)
        )
        assert r.status_code == 409
        assert r.json()["code"] == "HANDOVER_REQUIRED"


class TestHandover:
    pytestmark = asyncio_test

    async def test_opportunities_move(self, client, db):
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        row = await _reload(db, Opportunity, opp.id)
        assert row.submitted_by == w.colleague.id

    async def test_closed_deals_stay_with_the_person_who_did_them(self, client, db):
        w = await build(db)
        won = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.WON,
        )
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        row = await _reload(db, Opportunity, won.id)
        assert row.submitted_by == w.leaver.id

    async def test_managed_companies_move(self, client, db):
        w = await build(db)
        r = await client.post(
            f"/api/v1/users/{w.manager.id}/handover",
            headers=auth_header(w.superadmin),
            json={"to_user_id": w.other_admin.id},
        )
        assert r.status_code == 200, r.text[:300]
        row = await _reload(db, Company, w.company.id)
        assert row.channel_manager_id == w.other_admin.id

    async def test_poc_seats_and_stages_move(self, client, db):
        from app.services import poc_service

        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.colleague.id,
            status=OpportunityStatus.APPROVED,
        )
        poc = await make_poc(db, opportunity_id=opp.id, status=PocStatus.RUNNING)
        await make_team_member(
            db, poc_id=poc.id, user_id=w.rep.id, role=PocTeamRole.QA,
            assigned_by=w.manager.id,
        )
        await db.commit()
        await poc_service.set_stage_owner(db, poc.id, "deployment", w.rep.id, w.manager)
        await db.commit()

        await client.post(
            f"/api/v1/users/{w.rep.id}/handover",
            headers=auth_header(w.superadmin),
            json={"to_user_id": w.other_rep.id},
        )

        seat = (await db.execute(
            select(PocTeamMember).where(
                PocTeamMember.poc_id == poc.id, PocTeamMember.removed_at.is_(None)
            )
        )).scalar_one()
        await db.refresh(seat)
        assert seat.user_id == w.other_rep.id

        from app.models.poc import Poc

        row = await _reload(db, Poc, poc.id)
        assert row.deployment_owner_id == w.other_rep.id

    async def test_a_seat_the_successor_already_holds_is_closed_not_duplicated(
        self, client, db
    ):
        # Two active seats for one person on one POC breaks the roster index,
        # and nobody can hold two roles anyway.
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.colleague.id,
            status=OpportunityStatus.APPROVED,
        )
        poc = await make_poc(db, opportunity_id=opp.id, status=PocStatus.RUNNING)
        await make_team_member(
            db, poc_id=poc.id, user_id=w.rep.id, role=PocTeamRole.QA,
            assigned_by=w.manager.id,
        )
        await make_team_member(
            db, poc_id=poc.id, user_id=w.other_rep.id, role=PocTeamRole.SUPPORT,
            assigned_by=w.manager.id,
        )
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.rep.id}/handover",
            headers=auth_header(w.superadmin),
            json={"to_user_id": w.other_rep.id},
        )
        assert r.status_code == 200, r.text[:300]

        active = (await db.execute(
            select(PocTeamMember).where(
                PocTeamMember.poc_id == poc.id, PocTeamMember.removed_at.is_(None)
            )
        )).scalars().all()
        assert [m.user_id for m in active] == [w.other_rep.id]

    async def test_a_partners_pipeline_cannot_land_on_an_admin(self, client, db):
        # It would vanish: every partner-scoped query looks for a partner.
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        # As superadmin, so the scope check passes and the role guard is what
        # is actually under test — a channel manager would be refused first for
        # not managing the admin they picked.
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.superadmin),
            json={"to_user_id": w.other_admin.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "SUCCESSOR_NOT_PARTNER"

    async def test_a_pipeline_cannot_move_to_another_company(self, client, db):
        # It belongs to the company, not the person.
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.outsider.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "SUCCESSOR_WRONG_COMPANY"

    async def test_a_deactivated_successor_is_refused(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        w.colleague.status = UserStatus.INACTIVE
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "SUCCESSOR_INACTIVE"

    async def test_handing_over_to_yourself_is_refused(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.leaver.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "SAME_USER"

    async def test_an_out_of_scope_admin_cannot_hand_over(self, client, db):
        w = await build(db)
        stranger = await make_user(db, role=UserRole.ADMIN)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(stranger),
            json={"to_user_id": w.colleague.id},
        )
        assert r.status_code in (403, 404)

    async def test_a_partner_cannot_hand_anyone_over(self, client, db):
        w = await build(db)
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.colleague),
            json={"to_user_id": w.colleague.id},
        )
        assert r.status_code in (403, 404)


class TestRecord:
    pytestmark = asyncio_test

    async def test_the_handover_is_recorded_with_what_moved(self, client, db):
        w = await build(db)
        for _ in range(3):
            await make_opportunity(
                db, company_id=w.company.id, submitted_by=w.leaver.id,
                status=OpportunityStatus.PENDING_REVIEW,
            )
        await db.commit()

        await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id, "notes": "Left the company in August"},
        )

        r = await client.get(
            f"/api/v1/users/{w.leaver.id}/workload", headers=auth_header(w.manager)
        )
        entry = r.json()["history"][0]
        assert entry["to_user_name"] == w.colleague.full_name
        assert entry["moved"]["opportunities_submitted"] == 3
        assert entry["notes"] == "Left the company in August"

    async def test_the_successor_is_told(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.leaver.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        notes = await client.get(
            "/api/v1/notifications", headers=auth_header(w.colleague)
        )
        assert any(n["type"] == "work_handed_over" for n in notes.json()["items"])

    async def test_handing_over_nothing_is_refused(self, client, db):
        # Not an error worth hiding: it means the admin is on the wrong person.
        w = await build(db)
        r = await client.post(
            f"/api/v1/users/{w.leaver.id}/handover",
            headers=auth_header(w.manager),
            json={"to_user_id": w.colleague.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "NOTHING_TO_HAND_OVER"
