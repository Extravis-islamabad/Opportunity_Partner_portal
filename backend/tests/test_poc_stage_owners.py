"""Per-stage ownership, and what a partner may see of the team.

Two things are pinned here:

  1. A stage owner must be on the POC team, and stops being an owner the
     moment they leave it. A name against a stage is an answer to "who is
     responsible" — a stale one is worse than a blank.

  2. A partner viewing their own POC sees who is on the Extravis team and what
     each of them does, and nothing else: no work emails, no job titles, no
     assignment metadata, and not the per-stage division of labour.
"""
import pytest

from app.models.poc_team import PocTeamRole
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_opportunity,
    make_poc,
    make_team_member,
    make_user,
    requires_db,
)

pytestmark = [requires_db, pytest.mark.asyncio]


class World:
    pass


async def build_world(db):
    w = World()
    w.admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.company = await make_company(db, channel_manager_id=w.admin.id)

    w.owner_rep = await make_user(db, role=UserRole.SALES_REP)
    w.member_rep = await make_user(db, role=UserRole.SALES_REP)
    w.outsider_rep = await make_user(db, role=UserRole.SALES_REP)
    w.partner_user = await make_user(
        db, role=UserRole.PARTNER, company_id=w.company.id
    )

    w.opp = await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner_user.id
    )
    w.opp.sales_rep_id = w.owner_rep.id
    await db.flush()

    w.poc = await make_poc(db, opportunity_id=w.opp.id)
    await make_team_member(
        db, poc_id=w.poc.id, user_id=w.member_rep.id,
        role=PocTeamRole.DEPLOYMENT_ENGINEER, assigned_by=w.admin.id,
    )
    await db.commit()
    return w


def stage(body, key):
    return next(s for s in body["stages"] if s["key"] == key)


# ---------------------------------------------------------------------------
# Assigning an owner
# ---------------------------------------------------------------------------

class TestStageOwnership:
    async def test_a_team_member_can_be_made_stage_owner(self, client, db):
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=auth_header(w.admin),
            json={"owner_user_id": w.member_rep.id},
        )
        assert r.status_code == 200, r.text[:300]
        deployment = stage(r.json(), "deployment")
        assert deployment["owner_user_id"] == w.member_rep.id
        assert deployment["owner_name"] == w.member_rep.full_name
        assert deployment["owner_role_label"] == "Deployment Engineer"

    async def test_other_stages_are_untouched(self, client, db):
        # Five columns, one per stage — naming an owner for one must not smear
        # across the rest.
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=auth_header(w.admin),
            json={"owner_user_id": w.member_rep.id},
        )
        others = [s for s in r.json()["stages"] if s["key"] != "deployment"]
        assert all(s["owner_user_id"] is None for s in others)

    async def test_someone_off_the_team_cannot_own_a_stage(self, client, db):
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=auth_header(w.admin),
            json={"owner_user_id": w.outsider_rep.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "OWNER_NOT_ON_TEAM"

    async def test_an_owner_can_be_cleared(self, client, db):
        w = await build_world(db)
        headers = auth_header(w.admin)
        await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=headers, json={"owner_user_id": w.member_rep.id},
        )
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=headers, json={"owner_user_id": None},
        )
        assert r.status_code == 200
        assert stage(r.json(), "deployment")["owner_user_id"] is None

    async def test_an_unknown_stage_is_rejected(self, client, db):
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/tea_break/owner",
            headers=auth_header(w.admin),
            json={"owner_user_id": w.member_rep.id},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_STAGE"

    async def test_a_team_member_can_divide_up_the_work(self, client, db):
        # Not admin-only: ownership grants nothing (the owner is already on the
        # team), so anyone who can work the POC can say who does what.
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/dashboarding/owner",
            headers=auth_header(w.member_rep),
            json={"owner_user_id": w.member_rep.id},
        )
        assert r.status_code == 200, r.text[:300]

    async def test_an_outsider_cannot_set_an_owner(self, client, db):
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/dashboarding/owner",
            headers=auth_header(w.outsider_rep),
            json={"owner_user_id": w.member_rep.id},
        )
        assert r.status_code == 403

    async def test_leaving_the_team_unowns_their_stages(self, client, db):
        # The rule that keeps the tracker honest: no name against a stage from
        # somebody who is no longer on the POC.
        w = await build_world(db)
        headers = auth_header(w.admin)
        for key in ("deployment", "fine_tuning"):
            await client.put(
                f"/api/v1/pocs/{w.poc.id}/stages/{key}/owner",
                headers=headers, json={"owner_user_id": w.member_rep.id},
            )

        removed = await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}", headers=headers
        )
        assert removed.status_code == 200, removed.text[:300]

        after = await client.get(f"/api/v1/pocs/{w.poc.id}", headers=headers)
        assert all(s["owner_user_id"] is None for s in after.json()["stages"])

    async def test_rejoining_the_team_does_not_resurrect_old_ownership(self, client, db):
        # The assertion that actually pins the *clearing*. Rendering already
        # resolves owners against the live roster, so a stale column looks
        # unowned right up until that person rejoins — at which point the old
        # assignment would silently come back to life. Coming back onto a POC
        # must not silently make you responsible for what you used to own.
        w = await build_world(db)
        headers = auth_header(w.admin)
        await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=headers, json={"owner_user_id": w.member_rep.id},
        )
        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}", headers=headers
        )
        rejoined = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=headers,
            json={"user_id": w.member_rep.id, "role": "qa"},
        )
        assert rejoined.status_code == 201, rejoined.text[:300]

        after = await client.get(f"/api/v1/pocs/{w.poc.id}", headers=headers)
        assert stage(after.json(), "deployment")["owner_user_id"] is None


# ---------------------------------------------------------------------------
# What a partner sees
# ---------------------------------------------------------------------------

class TestPartnerSeesTeamAndNothingMore:
    async def test_partner_sees_names_and_roles(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/by-opportunity/{w.opp.id}",
            headers=auth_header(w.partner_user),
        )
        assert r.status_code == 200, r.text[:300]
        team = r.json()["team"]
        assert len(team) == 1
        assert team[0]["user_name"] == w.member_rep.full_name
        assert team[0]["role_label"] == "Deployment Engineer"

    async def test_partner_sees_nothing_more_about_them(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/by-opportunity/{w.opp.id}",
            headers=auth_header(w.partner_user),
        )
        member = r.json()["team"][0]
        for field in (
            "user_email", "job_title", "user_role",
            "assigned_by", "assigned_by_name", "assigned_at",
        ):
            assert member[field] is None, f"{field} leaked to a partner: {member[field]!r}"

    async def test_partner_does_not_see_stage_owners(self, client, db):
        w = await build_world(db)
        await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment/owner",
            headers=auth_header(w.admin),
            json={"owner_user_id": w.member_rep.id},
        )
        r = await client.get(
            f"/api/v1/pocs/by-opportunity/{w.opp.id}",
            headers=auth_header(w.partner_user),
        )
        for s in r.json()["stages"]:
            assert s["owner_user_id"] is None
            assert s["owner_name"] is None
            assert s["owner_role_label"] is None

    async def test_partner_still_sees_stage_progress(self, client, db):
        # Redaction is about who, not about how far along the POC is — the
        # partner's own POC progress must still be visible.
        w = await build_world(db)
        await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment",
            headers=auth_header(w.admin),
            json={"completed_at": "2026-09-01"},
        )
        r = await client.get(
            f"/api/v1/pocs/by-opportunity/{w.opp.id}",
            headers=auth_header(w.partner_user),
        )
        assert stage(r.json(), "deployment")["completed"] is True

    async def test_the_partners_poc_list_is_redacted_too(self, client, db):
        # The list goes through the same serialiser; a redaction that only
        # covered the detail route would leak on the way past.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs?page_size=100", headers=auth_header(w.partner_user)
        )
        assert r.status_code == 200
        row = next(p for p in r.json()["items"] if p["id"] == w.poc.id)
        assert row["team"][0]["user_email"] is None
        assert all(s["owner_name"] is None for s in row["stages"])

    async def test_staff_still_see_the_full_roster(self, client, db):
        # The control: redaction is for partners, not a blanket removal.
        w = await build_world(db)
        r = await client.get(f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.admin))
        member = r.json()["team"][0]
        assert member["user_email"] == w.member_rep.email
        assert member["assigned_at"] is not None
        assert member["assigned_by_name"] == w.admin.full_name

    async def test_a_partner_cannot_reach_the_activity_log(self, client, db):
        # "Nothing more than that" includes the work log behind the roster.
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities",
            headers=auth_header(w.partner_user),
        )
        assert r.status_code == 403
