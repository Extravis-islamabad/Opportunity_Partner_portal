"""Won/lost closure, review ageing, email visibility and the cleanup pass.

The assertions worth reading are the ones about *consequences* rather than
mechanics: that winning a deal does not remove it from the partner's approved
total, that a released review really does become editable again, and that a
send which never left the process is recorded rather than merely logged.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.opportunity import (
    ACCEPTED_STATUSES,
    LossReason,
    Opportunity,
    OpportunityStatus,
)
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_opportunity,
    make_user,
    requires_db,
)

# Applied per class rather than at module level: the settings tests below
# are plain synchronous functions, and marking those asyncio warns.
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
    await db.commit()
    return w


async def approved_opp(db, w):
    opp = await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner.id,
        status=OpportunityStatus.APPROVED,
    )
    await db.commit()
    return opp.id


# ---------------------------------------------------------------------------
# Won and lost
# ---------------------------------------------------------------------------

class TestClosure:
    pytestmark = asyncio_test

    async def test_close_as_won(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": True},
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["status"] == "won"
        assert body["loss_reason"] is None
        assert body["closed_outcome_at"] is not None

    async def test_close_as_lost_with_a_reason(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": False, "loss_reason": "competitor", "loss_notes": "Undercut on price"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "lost"
        assert r.json()["loss_reason"] == "competitor"
        assert r.json()["loss_reason_label"] == "Lost to competitor"
        assert r.json()["loss_notes"] == "Undercut on price"

    async def test_a_loss_needs_a_reason(self, client, db):
        # The point of the field is to be able to count it, so it cannot be
        # optional on the path that produces it.
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": False},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "LOSS_REASON_REQUIRED"

    async def test_an_invented_reason_is_rejected(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": False, "loss_reason": "vibes"},
        )
        assert r.status_code == 422

    async def test_only_an_approved_opportunity_can_close(self, client, db):
        w = await build(db)
        pending = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()
        r = await client.post(
            f"/api/v1/opportunities/{pending.id}/close",
            headers=auth_header(w.manager),
            json={"won": True},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "NOT_APPROVED"

    async def test_closing_twice_is_refused(self, client, db):
        # Re-closing would overwrite the reason recorded at the time.
        w = await build(db)
        opp = await approved_opp(db, w)
        headers = auth_header(w.manager)
        await client.post(
            f"/api/v1/opportunities/{opp}/close", headers=headers,
            json={"won": False, "loss_reason": "price"},
        )
        again = await client.post(
            f"/api/v1/opportunities/{opp}/close", headers=headers, json={"won": True}
        )
        assert again.status_code == 409
        assert again.json()["code"] == "ALREADY_CLOSED"

    async def test_a_partner_cannot_close_their_own_deal(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.partner),
            json={"won": True},
        )
        assert r.status_code in (403, 404)

    async def test_an_out_of_scope_admin_cannot_close(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.other_admin),
            json={"won": True},
        )
        assert r.status_code in (403, 404)

    async def test_winning_does_not_un_count_the_deal(self, client, db):
        # The trap in adding a status after APPROVED: everything that counted
        # `status == approved` would silently stop counting a won deal, so the
        # partner's approved total would go *down* when they won.
        from app.services import tier_service

        w = await build(db)
        opp = await approved_opp(db, w)
        before, _ = await tier_service.measure_company(db, w.company.id)
        assert before == 1

        await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager), json={"won": True},
        )
        await db.commit()

        after, _ = await tier_service.measure_company(db, w.company.id)
        assert after == 1, "winning a deal removed it from the approved count"

    async def test_losing_does_un_count_it(self, client, db):
        # The other half: a lost deal is not an accepted one.
        from app.services import tier_service

        w = await build(db)
        opp = await approved_opp(db, w)
        await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": False, "loss_reason": "no_budget"},
        )
        await db.commit()
        after, _ = await tier_service.measure_company(db, w.company.id)
        assert after == 0

    async def test_the_partner_is_told(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        await client.post(
            f"/api/v1/opportunities/{opp}/close",
            headers=auth_header(w.manager),
            json={"won": False, "loss_reason": "timing"},
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.partner))
        items = notes.json()["items"]
        assert any(n["type"] == "opportunity_lost" for n in items), items

    async def test_loss_reasons_are_reportable(self, client, db):
        # A superadmin's analytics count every lost deal in the database, so
        # this measures the delta rather than the absolute — other tests in the
        # suite lose deals too, and the breakdown is what is under test.
        w = await build(db)

        async def breakdown():
            r = await client.get(
                "/api/v1/dashboard/admin/analytics", headers=auth_header(w.superadmin)
            )
            assert r.status_code == 200, r.text[:300]
            return {b["reason"]: b["count"] for b in r.json()["loss_reasons"]}

        before = await breakdown()
        for reason in ("price", "price", "competitor"):
            opp = await approved_opp(db, w)
            await client.post(
                f"/api/v1/opportunities/{opp}/close",
                headers=auth_header(w.manager),
                json={"won": False, "loss_reason": reason},
            )

        after = await breakdown()
        assert after.get("price", 0) - before.get("price", 0) == 2
        assert after.get("competitor", 0) - before.get("competitor", 0) == 1

    async def test_the_reason_list_is_served(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/opportunities/loss-reasons", headers=auth_header(w.partner)
        )
        assert r.status_code == 200, r.text[:300]
        assert {o["value"] for o in r.json()} == {
            "price", "competitor", "no_budget", "timing", "technical_fit", "no_decision",
        }


# ---------------------------------------------------------------------------
# Review ageing and stuck claims
# ---------------------------------------------------------------------------

async def _claimed(db, w, *, days_ago: int):
    """An opportunity claimed for review N days ago."""
    opp = await make_opportunity(
        db, company_id=w.company.id, submitted_by=w.partner.id,
        status=OpportunityStatus.UNDER_REVIEW,
    )
    opp.reviewed_by = w.manager.id
    opp.review_claimed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    await db.commit()
    return opp.id


async def _ageing(db, opp_id):
    """What the sweep stamped on one opportunity.

    The sweep runs over every claimed review in the database, so its returned
    counts belong to the whole suite rather than to one test. These assertions
    are about the row the test created.
    """
    from sqlalchemy import select

    row = (await db.execute(
        select(Opportunity).where(Opportunity.id == opp_id)
    )).scalar_one()
    await db.refresh(row)
    return row.review_reminded_at, row.review_escalated_at


class TestReviewAgeing:
    pytestmark = asyncio_test

    async def test_opening_a_pending_opportunity_starts_the_clock(self, client, db):
        from sqlalchemy import select

        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.get(
            f"/api/v1/opportunities/{opp.id}", headers=auth_header(w.manager)
        )
        assert r.status_code == 200
        assert r.json()["status"] == "under_review"

        row = (await db.execute(
            select(Opportunity).where(Opportunity.id == opp.id)
        )).scalar_one()
        await db.refresh(row)
        assert row.review_claimed_at is not None

    async def test_a_fresh_claim_is_left_alone(self, client, db):
        from app.services.review_sla_service import sweep_stale_reviews

        w = await build(db)
        opp = await _claimed(db, w, days_ago=1)
        await sweep_stale_reviews(db)
        await db.commit()
        assert await _ageing(db, opp) == (None, None)

    async def test_an_ageing_claim_reminds_the_reviewer(self, client, db):
        from app.services.review_sla_service import sweep_stale_reviews

        w = await build(db)
        opp = await _claimed(db, w, days_ago=4)
        await sweep_stale_reviews(db)
        await db.commit()
        reminded_at, escalated_at = await _ageing(db, opp)
        assert reminded_at is not None
        assert escalated_at is None

        notes = await client.get("/api/v1/notifications", headers=auth_header(w.manager))
        assert any(n["type"] == "review_reminder" for n in notes.json()["items"])

    async def test_a_reminder_is_sent_once(self, client, db):
        # A nag that arrives every morning is a nag nobody reads.
        from app.services.review_sla_service import sweep_stale_reviews

        w = await build(db)
        opp = await _claimed(db, w, days_ago=4)
        await sweep_stale_reviews(db)
        await db.commit()
        first_stamp, _ = await _ageing(db, opp)
        assert first_stamp is not None

        await sweep_stale_reviews(db)
        await db.commit()
        assert (await _ageing(db, opp))[0] == first_stamp

    async def test_an_abandoned_claim_escalates_over_the_reviewer(self, client, db):
        from app.services.review_sla_service import sweep_stale_reviews

        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)
        await sweep_stale_reviews(db)
        await db.commit()
        reminded_at, escalated_at = await _ageing(db, opp)
        assert escalated_at is not None
        # Straight to escalation: a claim this old was never going to be
        # rescued by a reminder.
        assert reminded_at is None

        # The channel manager here *is* the reviewer, so the meaningful check
        # is that it went over their head to a superadmin.
        notes = await client.get(
            "/api/v1/notifications", headers=auth_header(w.superadmin)
        )
        assert any(n["type"] == "review_escalated" for n in notes.json()["items"])

    async def test_a_stuck_claim_is_listed(self, client, db):
        w = await build(db)
        opp = await _claimed(db, w, days_ago=10)
        r = await client.get(
            "/api/v1/opportunities/stale-reviews", headers=auth_header(w.superadmin)
        )
        assert r.status_code == 200, r.text[:300]
        rows = {row["id"]: row for row in r.json()}
        assert opp in rows
        assert rows[opp]["days_claimed"] >= 10

    async def test_releasing_puts_it_back_in_the_queue(self, client, db):
        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.superadmin),
            json={"reason": "Reviewer on leave"},
        )
        assert r.status_code == 200, r.text[:300]

        detail = await client.get(
            f"/api/v1/opportunities/{opp}", headers=auth_header(w.superadmin)
        )
        # Superadmin reads re-claim it, so check the DB rather than the read.
        from sqlalchemy import select

        row = (await db.execute(select(Opportunity).where(Opportunity.id == opp))).scalar_one()
        await db.refresh(row)
        assert row.reviewed_by != w.manager.id or row.review_claimed_at is not None
        assert detail.status_code == 200

    async def test_release_frees_the_partner_to_edit_again(self, client, db):
        # The consequence that matters: a frozen deal becomes workable again.
        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)

        blocked = await client.put(
            f"/api/v1/opportunities/{opp}",
            headers=auth_header(w.partner), json={"name": "Amended"},
        )
        assert blocked.status_code == 409

        await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.superadmin), json={},
        )
        allowed = await client.put(
            f"/api/v1/opportunities/{opp}",
            headers=auth_header(w.partner), json={"name": "Amended"},
        )
        assert allowed.status_code == 200, allowed.text[:300]

    async def test_release_clears_the_ageing_trail(self, client, db):
        # The next reviewer gets their own grace period rather than inheriting
        # a clock already past escalation.
        from sqlalchemy import select

        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)
        # Sweep first, so there is an actual trail to clear: asserting these
        # are None on a row nothing ever stamped proves nothing.
        from app.services.review_sla_service import sweep_stale_reviews

        await sweep_stale_reviews(db)
        await db.commit()
        assert (await _ageing(db, opp))[1] is not None

        # A real row this old was reminded first and escalated later; stamp the
        # earlier half so both fields are under test.
        stamped = (await db.execute(
            select(Opportunity).where(Opportunity.id == opp)
        )).scalar_one()
        stamped.review_reminded_at = datetime.now(timezone.utc) - timedelta(days=20)
        await db.commit()

        await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.superadmin), json={},
        )
        row = (await db.execute(select(Opportunity).where(Opportunity.id == opp))).scalar_one()
        await db.refresh(row)
        assert row.review_claimed_at is None
        assert row.review_reminded_at is None
        assert row.review_escalated_at is None

    async def test_the_previous_reviewer_is_told(self, client, db):
        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)
        await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.superadmin),
            json={"reason": "On leave"},
        )
        notes = await client.get("/api/v1/notifications", headers=auth_header(w.manager))
        assert any(n["type"] == "review_released" for n in notes.json()["items"])

    async def test_only_an_under_review_opportunity_can_be_released(self, client, db):
        w = await build(db)
        opp = await approved_opp(db, w)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.superadmin), json={},
        )
        assert r.status_code == 400

    async def test_an_out_of_scope_admin_cannot_release(self, client, db):
        w = await build(db)
        opp = await _claimed(db, w, days_ago=30)
        r = await client.post(
            f"/api/v1/opportunities/{opp}/release",
            headers=auth_header(w.other_admin), json={},
        )
        assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Email visibility
# ---------------------------------------------------------------------------

class TestEmailVisibility:
    pytestmark = asyncio_test

    async def test_a_skipped_send_is_recorded(self, client, db):
        # The test environment has no SMTP configured, which is exactly the
        # production failure this feature exists to make visible.
        from sqlalchemy import func, select

        from app.models.email_delivery import EmailDelivery, EmailStatus
        from app.utils.email import send_template_email

        before = (await db.execute(
            select(func.count(EmailDelivery.id))
        )).scalar() or 0

        sent = await send_template_email(
            ["nobody@fixture.example.com"], "Test subject", "notification",
            {"name": "X", "title": "T", "message": "M"},
        )
        assert sent is False

        after = (await db.execute(
            select(EmailDelivery).order_by(EmailDelivery.id.desc()).limit(1)
        )).scalar_one()
        assert after.status == EmailStatus.SKIPPED
        assert after.subject == "Test subject"
        assert after.template == "notification"
        assert "SMTP" in (after.error or "")
        assert ((await db.execute(select(func.count(EmailDelivery.id)))).scalar() or 0) > before

    async def test_the_log_is_superadmin_only(self, client, db):
        w = await build(db)
        for actor in (w.partner, w.manager):
            r = await client.get("/api/v1/email-log", headers=auth_header(actor))
            assert r.status_code in (403, 404)

    async def test_the_log_reports_configuration(self, client, db):
        w = await build(db)
        r = await client.get("/api/v1/email-log", headers=auth_header(w.superadmin))
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # The page can say *why* everything is being skipped rather than
        # leaving it to be guessed from the rows.
        assert body["email_configured"] is False
        assert "skipped" in body["totals_by_status"]


class TestEmailConfiguration:
    """Settings-level, no database and no event loop: what counts as
    configured, and what production refuses to start without."""

    def test_production_refuses_to_boot_without_email(self):
        from app.core.config import Settings

        with pytest.raises(ValueError) as exc:
            Settings(
                APP_ENV="production",
                JWT_SECRET_KEY="x" * 40,
                SUPERADMIN_PASSWORD="a-real-password",
            )
        assert "SMTP" in str(exc.value)

    def test_production_boots_with_email(self):
        from app.core.config import Settings

        s = Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="x" * 40,
            SUPERADMIN_PASSWORD="a-real-password",
            SMTP_HOST="smtp.example.com",
            SMTP_PASSWORD="pw",
            SMTP_FROM_EMAIL="noreply@example.com",
        )
        assert s.email_is_configured

    def test_a_password_alone_is_not_configured(self):
        # The old check tested SMTP_PASSWORD only, so a deployment with a
        # password and no host looked configured and failed at connect time.
        from app.core.config import Settings

        s = Settings(SMTP_PASSWORD="pw", SMTP_HOST="")
        assert s.email_is_configured is False


# ---------------------------------------------------------------------------
# Cleanup: the filters that used to lie
# ---------------------------------------------------------------------------

class TestServerSideFilters:
    pytestmark = asyncio_test

    async def test_product_filter_is_applied_to_the_whole_set(self, client, db):
        # Filtering client-side meant `total` described the unfiltered set
        # while the rows described the filtered one, and a match on page 2 was
        # invisible. 25 rows forces more than one page.
        w = await build(db)
        for i in range(25):
            await make_opportunity(
                db, company_id=w.company.id, submitted_by=w.partner.id,
                status=OpportunityStatus.APPROVED,
                products=["MonetX" if i == 24 else "SupportX"],
            )
        await db.commit()

        # Narrowed to this test's own company: a superadmin otherwise reads
        # every MonetX deal in the database, and the exact total is the point.
        r = await client.get(
            f"/api/v1/opportunities?product=MonetX&page_size=20&company_id={w.company.id}",
            headers=auth_header(w.superadmin),
        )
        assert r.status_code == 200
        body = r.json()
        # One match, on what would have been page 2 before the fix.
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["product"] == "MonetX"

    async def test_industry_and_quarter_filter_server_side(self, client, db):
        w = await build(db)
        opp = await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.APPROVED,
        )
        opp.industry = "Banking"
        opp.time_frame = "Q3"
        await db.commit()

        hit = await client.get(
            "/api/v1/opportunities?industry=Banking&time_frame=Q3",
            headers=auth_header(w.superadmin),
        )
        assert hit.json()["total"] >= 1

        miss = await client.get(
            "/api/v1/opportunities?industry=Banking&time_frame=Q4",
            headers=auth_header(w.superadmin),
        )
        assert opp.id not in {i["id"] for i in miss.json()["items"]}

    async def test_accepted_statuses_is_the_single_definition(self):
        # Anything counting "approved opportunities" must go through this, or
        # a won deal drops out of the count.
        assert set(ACCEPTED_STATUSES) == {
            OpportunityStatus.APPROVED,
            OpportunityStatus.WON,
        }
