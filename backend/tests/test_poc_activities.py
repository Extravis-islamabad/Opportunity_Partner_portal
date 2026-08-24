"""A POC's activity log — who actually did what.

The team roster answers "who is assigned". This answers "who has logged
work", which is the question the feature was asked for, and the two do not
have the same answer. So the assertions here are mostly about the gap between
them: a member with nothing logged still appears (with a zero), and someone
who logged work and has since left the team still appears (flagged).

Also pinned: an activity cannot be filed against a POC the logger has no
business in, because a work log anyone can write themselves into is not
evidence of anything.
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
    w.idle_rep = await make_user(db, role=UserRole.SALES_REP)
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
    for user, role in (
        (w.member_rep, PocTeamRole.DEPLOYMENT_ENGINEER),
        # Assigned but logs nothing — the case the feed has to surface.
        (w.idle_rep, PocTeamRole.QA),
    ):
        await make_team_member(
            db, poc_id=w.poc.id, user_id=user.id, role=role, assigned_by=w.admin.id
        )
    await db.commit()
    return w


async def log_activity(client, user, *, poc_id=None, opportunity_id=None,
                       minutes=60, activity_type="demo", date="2026-08-20"):
    body = {
        "activity_date": date,
        "activity_type": activity_type,
        "duration_minutes": minutes,
    }
    if poc_id is not None:
        body["poc_id"] = poc_id
    if opportunity_id is not None:
        body["opportunity_id"] = opportunity_id
    return await client.post("/api/v1/activities", headers=auth_header(user), json=body)


def person(feed, user_id):
    return next(p for p in feed["by_person"] if p["user_id"] == user_id)


# ---------------------------------------------------------------------------
# The feed
# ---------------------------------------------------------------------------

class TestPocActivityFeed:
    async def test_poc_linked_activity_appears(self, client, db):
        w = await build_world(db)
        created = await log_activity(client, w.member_rep, poc_id=w.poc.id)
        assert created.status_code == 201, created.text[:300]

        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )
        assert r.status_code == 200, r.text[:300]
        feed = r.json()
        assert feed["total_activities"] == 1
        assert feed["items"][0]["linked_via"] == "poc"

    async def test_opportunity_linked_activity_appears_and_is_labelled(self, client, db):
        # Activity logged against the deal is activity on the same engagement,
        # but it is a different claim from "this was POC work" — so it counts
        # and says which link brought it in.
        w = await build_world(db)
        await log_activity(client, w.owner_rep, opportunity_id=w.opp.id)

        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )
        feed = r.json()
        assert feed["total_activities"] == 1
        assert feed["items"][0]["linked_via"] == "opportunity"

    async def test_an_activity_linked_both_ways_counts_once(self, client, db):
        # The OR must not double-count: it is one row either way.
        w = await build_world(db)
        await log_activity(
            client, w.member_rep, poc_id=w.poc.id, opportunity_id=w.opp.id
        )
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )
        feed = r.json()
        assert feed["total_activities"] == 1
        # The stronger claim wins the label.
        assert feed["items"][0]["linked_via"] == "poc"

    async def test_unrelated_activity_does_not_appear(self, client, db):
        w = await build_world(db)
        await log_activity(client, w.outsider_rep)  # no links at all

        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )
        assert r.json()["total_activities"] == 0

    async def test_totals_per_person(self, client, db):
        w = await build_world(db)
        await log_activity(client, w.member_rep, poc_id=w.poc.id, minutes=90)
        await log_activity(
            client, w.member_rep, poc_id=w.poc.id, minutes=45,
            activity_type="call", date="2026-08-21",
        )
        await log_activity(client, w.owner_rep, opportunity_id=w.opp.id, minutes=30)

        feed = (await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )).json()

        assert feed["total_activities"] == 3
        assert feed["total_duration_minutes"] == 165

        member = person(feed, w.member_rep.id)
        assert member["activity_count"] == 2
        assert member["total_duration_minutes"] == 135
        assert member["poc_role_label"] == "Deployment Engineer"
        assert member["on_team"] is True

        assert person(feed, w.owner_rep.id)["activity_count"] == 1

    async def test_an_assigned_member_with_nothing_logged_still_appears(self, client, db):
        # The point of the view: "assigned but nothing recorded" is a finding,
        # not an absence.
        w = await build_world(db)
        await log_activity(client, w.member_rep, poc_id=w.poc.id)

        feed = (await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )).json()
        idle = person(feed, w.idle_rep.id)
        assert idle["activity_count"] == 0
        assert idle["total_duration_minutes"] == 0
        assert idle["poc_role_label"] == "QA"
        assert idle["on_team"] is True

    async def test_someone_who_left_the_team_keeps_their_totals(self, client, db):
        # Their work happened. Removing them from the roster must not erase it,
        # but the feed says they are no longer on the team.
        w = await build_world(db)
        await log_activity(client, w.member_rep, poc_id=w.poc.id, minutes=120)
        await client.delete(
            f"/api/v1/pocs/{w.poc.id}/team/{w.member_rep.id}",
            headers=auth_header(w.admin),
        )

        feed = (await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )).json()
        past = person(feed, w.member_rep.id)
        assert past["activity_count"] == 1
        assert past["total_duration_minutes"] == 120
        assert past["on_team"] is False

    async def test_team_members_are_listed_before_outsiders(self, client, db):
        w = await build_world(db)
        await log_activity(client, w.owner_rep, opportunity_id=w.opp.id)

        feed = (await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )).json()
        on_team_flags = [p["on_team"] for p in feed["by_person"]]
        # Everyone on the team comes first, so the view reads as "the team and
        # what they did" rather than a list of whoever happened to log.
        assert on_team_flags == sorted(on_team_flags, reverse=True)

    async def test_a_deleted_activity_drops_out(self, client, db):
        w = await build_world(db)
        created = await log_activity(client, w.member_rep, poc_id=w.poc.id)
        await client.delete(
            f"/api/v1/activities/{created.json()['id']}",
            headers=auth_header(w.member_rep),
        )
        feed = (await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.admin)
        )).json()
        assert feed["total_activities"] == 0
        assert person(feed, w.member_rep.id)["activity_count"] == 0


# ---------------------------------------------------------------------------
# Who may link, and who may look
# ---------------------------------------------------------------------------

class TestActivityLinkAuthorisation:
    async def test_a_team_member_can_link_to_their_poc(self, client, db):
        w = await build_world(db)
        r = await log_activity(client, w.member_rep, poc_id=w.poc.id)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["poc_id"] == w.poc.id

    async def test_an_outsider_cannot_write_themselves_into_a_poc_log(self, client, db):
        # Without this the log records whatever anyone claims, which is worth
        # nothing as evidence of who did the work.
        w = await build_world(db)
        r = await log_activity(client, w.outsider_rep, poc_id=w.poc.id)
        assert r.status_code == 403

    async def test_an_unknown_poc_is_rejected(self, client, db):
        w = await build_world(db)
        r = await log_activity(client, w.member_rep, poc_id=999999)
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_POC"

    async def test_the_link_can_be_added_by_editing(self, client, db):
        w = await build_world(db)
        created = await log_activity(client, w.member_rep)
        assert created.json()["poc_id"] is None

        r = await client.put(
            f"/api/v1/activities/{created.json()['id']}",
            headers=auth_header(w.member_rep),
            json={"poc_id": w.poc.id},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["poc_id"] == w.poc.id

    async def test_editing_cannot_smuggle_in_a_foreign_poc(self, client, db):
        w = await build_world(db)
        created = await log_activity(client, w.outsider_rep)
        r = await client.put(
            f"/api/v1/activities/{created.json()['id']}",
            headers=auth_header(w.outsider_rep),
            json={"poc_id": w.poc.id},
        )
        assert r.status_code == 403

    async def test_an_outsider_cannot_read_the_feed(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities",
            headers=auth_header(w.outsider_rep),
        )
        assert r.status_code == 403

    async def test_a_team_member_can_read_the_feed(self, client, db):
        w = await build_world(db)
        r = await client.get(
            f"/api/v1/pocs/{w.poc.id}/activities", headers=auth_header(w.member_rep)
        )
        assert r.status_code == 200, r.text[:300]
