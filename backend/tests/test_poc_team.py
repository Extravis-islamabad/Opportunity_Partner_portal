"""End-to-end tests for the POC team.

The point of the roster is that membership *grants access*. Before it, only
the opportunity's one named sales rep could touch a POC, so anyone else put on
it was refused by the very check that was supposed to let them work. Most of
what follows is about that: a team member can do the job, and the widening
stops exactly where it should.

The world each test builds:

    Opportunity ── owned by  owner_rep     (Opportunity.sales_rep_id)
                └─ POC ──┬── member_rep    (deployment engineer, on the team)
                         └── (outsider_rep is on nothing)

`outsider_rep` is the control: every permission test that passes for
member_rep is also run for them, because "the team member can do X" only means
something if a non-member cannot.
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
    """The fixture world, with the ids each test asserts on."""


async def build_world(db, *, with_member=True):
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

    if with_member:
        await make_team_member(
            db,
            poc_id=w.poc.id,
            user_id=w.member_rep.id,
            role=PocTeamRole.DEPLOYMENT_ENGINEER,
            assigned_by=w.admin.id,
        )

    # The app runs its own session; nothing above is visible until committed.
    await db.commit()
    return w


# ---------------------------------------------------------------------------
# The bug this feature exists to fix
# ---------------------------------------------------------------------------

class TestTeamMemberCanWork:
    async def test_member_can_read_the_poc(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200, r.text[:300]

    async def test_outsider_still_cannot_read_the_poc(self, client, db):
        # The control. Without this, the test above would pass on a check
        # that had simply been removed.
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.outsider_rep)
        )
        assert r.status_code == 403

    async def test_member_can_tick_a_stage(self, client, db):
        # The concrete thing a deployment engineer is added to a POC to do.
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment",
            headers=auth_header(w.member_rep),
            json={"completed_at": "2026-09-01"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["deployment_completed_at"] == "2026-09-01"

    async def test_outsider_cannot_tick_a_stage(self, client, db):
        w = await build_world(db)
        r = await client.put(
            f"/api/v1/pocs/{w.poc.id}/stages/deployment",
            headers=auth_header(w.outsider_rep),
            json={"completed_at": "2026-09-01"},
        )
        assert r.status_code == 403

    async def test_member_can_update_and_close_the_poc(self, client, db):
        w = await build_world(db)
        headers = auth_header(w.member_rep)

        updated = await client.put(
            f"/api/v1/pocs/{w.poc.id}",
            headers=headers,
            json={"notes": "Rack cabling done, moving to onboarding."},
        )
        assert updated.status_code == 200, updated.text[:300]

        closed = await client.post(
            f"/api/v1/pocs/{w.poc.id}/close",
            headers=headers,
            json={"successful": True, "end_date": "2026-10-01"},
        )
        assert closed.status_code == 200, closed.text[:300]
        assert closed.json()["status"] == "successful"

    async def test_member_can_open_the_parent_opportunity(self, client, db):
        # The POC panel lives on the opportunity page. A member who gets a 403
        # here cannot reach the POC at all through the UI, however open the
        # POC endpoints are.
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/opportunities/{w.opp.id}", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200, r.text[:300]

    async def test_outsider_cannot_open_the_parent_opportunity(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/opportunities/{w.opp.id}",
            headers=auth_header(w.outsider_rep),
        )
        assert r.status_code == 403

    async def test_removal_ends_access_immediately(self, client, db):
        w = await build_world(db)
        assert (
            await client.get(
                f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.member_rep)
            )
        ).status_code == 200

        removed = await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=auth_header(w.admin),
        )
        assert removed.status_code == 200, removed.text[:300]

        after = await client.get(
            f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.member_rep)
        )
        assert after.status_code == 403


# ---------------------------------------------------------------------------
# Where the widening stops
# ---------------------------------------------------------------------------

class TestMembershipDoesNotLeak:
    async def test_member_cannot_approve_the_opportunity(self, client, db):
        # Membership grants POC work and opportunity *reading*. Approval is an
        # admin route; a sales rep must not reach it however they got here.
        w = await build_world(db)
        r = await client.post(
            f"/api/v1/opportunities/{w.opp.id}/approve",
            headers=auth_header(w.member_rep),
            json={},
        )
        assert r.status_code == 403

    async def test_member_cannot_enlarge_the_team(self, client, db):
        # Staffing is an admin decision. If a member could add people, one
        # assignment would be enough to hand out access indefinitely.
        w = await build_world(db)
        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.member_rep),
            json={"user_id": w.outsider_rep.id, "role": "qa"},
        )
        assert r.status_code == 403

    async def test_the_owning_rep_cannot_staff_their_own_poc(self, client, db):
        # The one that actually pins "admin-only". A non-member sales rep is
        # refused by the per-record check too, so testing with one would pass
        # even if the route admitted every sales rep; the *owning* rep passes
        # that check and is stopped only by the role guard.
        w = await build_world(db, with_member=False)
        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.owner_rep),
            json={"user_id": w.member_rep.id, "role": "qa"},
        )
        assert r.status_code == 403

    async def test_the_owning_rep_cannot_remove_someone(self, client, db):
        w = await build_world(db)
        r = await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=auth_header(w.owner_rep),
        )
        assert r.status_code == 403

    async def test_a_channel_manager_cannot_staff_a_poc_outside_their_scope(
        self, client, db
    ):
        # add_poc_team_member uses the *strict* check, so an admin who does
        # not manage the company cannot put themselves on the POC and thereby
        # widen their own access.
        w = await build_world(db)
        stranger_admin = await make_user(db, role=UserRole.ADMIN)
        await db.commit()

        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(stranger_admin),
            json={"user_id": stranger_admin.id, "role": "project_manager"},
        )
        assert r.status_code == 403

    async def test_membership_does_not_widen_the_opportunity_list(self, client, db):
        # Reading one opportunity is not the same as being assigned to it. The
        # rep's pipeline list stays their own.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/opportunities?page_size=100", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200
        assert w.opp.id not in {item["id"] for item in r.json()["items"]}

    async def test_a_partner_cannot_be_put_on_a_team(self, client, db):
        # A partner is on the other side of the deal. A membership would hand
        # them write access to the POC.
        w = await build_world(db)
        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.admin),
            json={"user_id": w.partner_user.id, "role": "qa"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INELIGIBLE_TEAM_MEMBER"


# ---------------------------------------------------------------------------
# Managing the roster
# ---------------------------------------------------------------------------

class TestTeamManagement:
    async def test_admin_can_add_change_role_and_remove(self, client, db):
        w = await build_world(db, with_member=False)
        headers = auth_header(w.admin)

        added = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=headers,
            json={"user_id": w.member_rep.id, "role": "solution_architect"},
        )
        assert added.status_code == 201, added.text[:300]
        assert added.json()["role"] == "solution_architect"
        assert added.json()["role_label"] == "Solution Architect"
        assert added.json()["user_name"] == w.member_rep.full_name

        changed = await client.put(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=headers,
            json={"role": "qa"},
        )
        assert changed.status_code == 200, changed.text[:300]
        # "QA", not "Qa" — the label table exists for exactly this.
        assert changed.json()["role_label"] == "QA"
        # Same membership row, so the person never lost access mid-change.
        assert changed.json()["id"] == added.json()["id"]

        roster = await client.get(f"/api/v1/pocs/{w.poc.id}/team", headers=headers)
        assert [m["user_id"] for m in roster.json()] == [w.member_rep.id]

        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}", headers=headers
        )
        assert (await client.get(
            f"/api/v1/pocs/{w.poc.id}/team", headers=headers
        )).json() == []

    async def test_removed_members_survive_in_the_history(self, client, db):
        w = await build_world(db)
        headers = auth_header(w.admin)
        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}", headers=headers
        )

        history = await client.get(
            f"/api/v1/pocs/{w.poc.id}/team?include_removed=true", headers=headers
        )
        assert history.status_code == 200
        rows = history.json()
        assert len(rows) == 1
        assert rows[0]["user_id"] == w.member_rep.id
        assert rows[0]["removed_at"] is not None

    async def test_someone_can_be_re_added_after_removal(self, client, db):
        # The unique index is partial, so the row left behind by a removal
        # must not block putting the person back on later.
        w = await build_world(db)
        headers = auth_header(w.admin)
        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}", headers=headers
        )

        again = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=headers,
            json={"user_id": w.member_rep.id, "role": "support"},
        )
        assert again.status_code == 201, again.text[:300]

        history = await client.get(
            f"/api/v1/pocs/{w.poc.id}/team?include_removed=true", headers=headers
        )
        # Two spells, not one rewritten row.
        assert len(history.json()) == 2

    async def test_adding_the_same_person_twice_is_a_conflict(self, client, db):
        w = await build_world(db)
        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.admin),
            json={"user_id": w.member_rep.id, "role": "qa"},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "ALREADY_ON_TEAM"

    async def test_an_unknown_role_is_rejected(self, client, db):
        w = await build_world(db, with_member=False)
        r = await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.admin),
            json={"user_id": w.member_rep.id, "role": "chief_vibes_officer"},
        )
        assert r.status_code == 422

    async def test_the_role_options_endpoint_lists_all_six(self, client, db):
        w = await build_world(db)
        r = await client.get("/api/v1/pocs/team/roles", headers=auth_header(w.admin))
        assert r.status_code == 200, r.text[:300]
        assert {o["value"] for o in r.json()} == {
            "presales_lead", "solution_architect", "deployment_engineer",
            "project_manager", "qa", "support",
        }

    async def test_assignable_users_are_staff_only(self, client, db):
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs/team/assignable-users", headers=auth_header(w.admin)
        )
        assert r.status_code == 200, r.text[:300]
        ids = {u["id"] for u in r.json()}
        assert w.member_rep.id in ids
        assert w.admin.id in ids
        assert w.partner_user.id not in ids


# ---------------------------------------------------------------------------
# Notification and visibility
# ---------------------------------------------------------------------------

class TestAssignmentIsVisible:
    async def test_the_assignee_is_notified(self, client, db):
        w = await build_world(db, with_member=False)
        await client.post(
            f"/api/v1/pocs/{w.poc.id}/team",
            headers=auth_header(w.admin),
            json={"user_id": w.member_rep.id, "role": "presales_lead"},
        )

        notes = await client.get(
            "/api/v1/notifications", headers=auth_header(w.member_rep)
        )
        assert notes.status_code == 200, notes.text[:300]
        items = notes.json()["items"]
        assert any(n["type"] == "poc_team_assigned" for n in items), items
        assigned = next(n for n in items if n["type"] == "poc_team_assigned")
        # Deep-links to the opportunity, which is where the POC panel lives.
        assert assigned["entity_type"] == "opportunity"
        assert assigned["entity_id"] == w.opp.id
        assert "Presales Lead" in assigned["message"]

    async def test_a_role_change_is_notified(self, client, db):
        w = await build_world(db)
        await client.put(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=auth_header(w.admin),
            json={"role": "project_manager"},
        )
        notes = await client.get(
            "/api/v1/notifications", headers=auth_header(w.member_rep)
        )
        assert any(
            n["type"] == "poc_team_role_changed" for n in notes.json()["items"]
        )

    async def test_assigned_pocs_appear_in_the_members_list(self, client, db):
        # The dashboard requirement: a POC someone is on has to show up for
        # them, not only for the opportunity's named rep.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs?page_size=100", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200, r.text[:300]
        assert w.poc.id in {p["id"] for p in r.json()["items"]}

    async def test_an_outsiders_list_stays_empty(self, client, db):
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs?page_size=100", headers=auth_header(w.outsider_rep)
        )
        assert r.status_code == 200
        assert w.poc.id not in {p["id"] for p in r.json()["items"]}

    async def test_the_owning_rep_still_sees_their_own_poc(self, client, db):
        # Widening for team members must not have replaced the original
        # ground for access.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs?page_size=100", headers=auth_header(w.owner_rep)
        )
        assert w.poc.id in {p["id"] for p in r.json()["items"]}

    async def test_the_summary_counters_include_assigned_pocs(self, client, db):
        # The counters back the dashboard cards; they must agree with the list
        # beside them.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/dashboard/poc-summary", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200, r.text[:300]
        running = next(s for s in r.json()["by_status"] if s["status"] == "running")
        assert running["count"] >= 1

    async def test_an_outsiders_counters_stay_zero(self, client, db):
        w = await build_world(db)
        r = await client.get(
            "/api/v1/dashboard/poc-summary", headers=auth_header(w.outsider_rep)
        )
        assert r.status_code == 200
        assert sum(s["count"] for s in r.json()["by_status"]) == 0

    async def test_a_superadmin_still_sees_every_poc(self, client, db):
        # The trap in the OR'd scope: handing a superadmin a team-membership
        # ground would narrow them to their own POCs instead of widening
        # anything. They must pass no grounds at all.
        w = await build_world(db)
        r = await client.get(
            "/api/v1/pocs?page_size=100", headers=auth_header(w.admin)
        )
        assert r.status_code == 200
        assert w.poc.id in {p["id"] for p in r.json()["items"]}

    async def test_the_poc_response_carries_the_roster(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.admin)
        )
        assert r.status_code == 200
        team = r.json()["team"]
        assert [m["user_id"] for m in team] == [w.member_rep.id]
        assert team[0]["role_label"] == "Deployment Engineer"
        assert team[0]["assigned_by_name"] == w.admin.full_name

    async def test_removed_members_are_absent_from_the_roster_field(self, client, db):
        w = await build_world(db)
        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=auth_header(w.admin),
        )
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}", headers=auth_header(w.admin)
        )
        assert r.json()["team"] == []
