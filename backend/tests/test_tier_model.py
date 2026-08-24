"""One tier model.

There were three sets of rules and three "progress to gold" numbers, only one
of which could actually promote anyone. These tests pin the surviving rules and
— more importantly — pin that every screen now reads from them, because three
implementations agreeing today is worth nothing if they can drift again
tomorrow.

The threshold tests need no database. The agreement tests do, because the point
is that three separate endpoints return consistent numbers.
"""
import pytest

from app.models.company import PartnerTier
from app.models.opportunity import OpportunityStatus
from app.models.user import UserRole
from app.services import tier_service
from tests.conftest import (
    auth_header,
    make_company,
    make_course,
    make_enrollment,
    make_opportunity,
    make_user,
    requires_db,
)


# ---------------------------------------------------------------------------
# The rules themselves
# ---------------------------------------------------------------------------

class TestQualifyingTier:
    @pytest.mark.parametrize("opps,lms,expected", [
        (0, 0.0, "silver"),
        (9, 100.0, "silver"),     # opportunities short
        (10, 49.9, "silver"),     # training short
        (10, 50.0, "gold"),       # exactly on both
        (19, 79.0, "gold"),
        (20, 79.9, "gold"),       # training short of platinum
        (19, 100.0, "gold"),      # opportunities short of platinum
        (20, 80.0, "platinum"),   # exactly on both
        (500, 100.0, "platinum"),
    ])
    def test_thresholds(self, opps, lms, expected):
        assert tier_service.qualifying_tier(opps, lms).value == expected

    def test_both_criteria_are_required(self):
        # The failure mode worth naming: neither criterion alone is enough,
        # which is what made "5 opportunities OR 3 courses" style rules wrong.
        assert tier_service.qualifying_tier(1000, 0.0) == PartnerTier.SILVER
        assert tier_service.qualifying_tier(0, 100.0) == PartnerTier.SILVER

    def test_promotion_ordering(self):
        assert tier_service.is_promotion(PartnerTier.SILVER, PartnerTier.GOLD)
        assert tier_service.is_promotion(PartnerTier.GOLD, PartnerTier.PLATINUM)
        assert not tier_service.is_promotion(PartnerTier.GOLD, PartnerTier.SILVER)
        assert not tier_service.is_promotion(PartnerTier.GOLD, PartnerTier.GOLD)

    def test_next_tier(self):
        assert tier_service.next_tier(PartnerTier.SILVER) == PartnerTier.GOLD
        assert tier_service.next_tier(PartnerTier.GOLD) == PartnerTier.PLATINUM
        assert tier_service.next_tier(PartnerTier.PLATINUM) is None


class TestStanding:
    def test_headline_is_the_weaker_criterion(self):
        # All the training, none of the pipeline. Averaging would report 50%
        # and flatter a company that cannot promote at all.
        s = tier_service.standing(PartnerTier.SILVER, 0, 100.0)
        assert s.lms_progress_pct == 100.0
        assert s.opps_progress_pct == 0.0
        assert s.overall_progress_pct == 0.0

    def test_progress_is_capped(self):
        s = tier_service.standing(PartnerTier.SILVER, 999, 100.0)
        assert s.opps_progress_pct == 100.0
        assert s.overall_progress_pct == 100.0

    def test_platinum_has_nothing_left_to_reach(self):
        s = tier_service.standing(PartnerTier.PLATINUM, 25, 90.0)
        assert s.next_tier is None
        assert s.opps_required == 0
        assert s.overall_progress_pct == 100.0

    def test_requirements_are_for_the_next_tier_not_the_current_one(self):
        # A gold company's bar must measure the distance to platinum, not
        # re-report the gold thresholds it already cleared.
        s = tier_service.standing(PartnerTier.GOLD, 10, 50.0)
        assert s.next_tier == PartnerTier.PLATINUM
        assert s.opps_required == 20
        assert s.lms_rate_required == 80.0

    def test_qualifies_for_is_independent_of_the_tier_held(self):
        # A company sitting at silver on platinum numbers still reports
        # qualifying for platinum — the promotion decision is separate.
        s = tier_service.standing(PartnerTier.SILVER, 20, 80.0)
        assert s.current == PartnerTier.SILVER
        assert s.qualifies_for == PartnerTier.PLATINUM


# ---------------------------------------------------------------------------
# Every screen reads from those rules
# ---------------------------------------------------------------------------

pytestmark_db = [requires_db, pytest.mark.asyncio]


@requires_db
@pytest.mark.asyncio
class TestScreensAgree:
    async def _world(self, db, *, approved_opps: int, courses: int, done: int):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(db, channel_manager_id=admin.id)
        partner = await make_user(
            db, role=UserRole.PARTNER, company_id=company.id
        )
        for _ in range(approved_opps):
            await make_opportunity(
                db, company_id=company.id, submitted_by=partner.id,
                status=OpportunityStatus.APPROVED,
            )
        for i in range(courses):
            course = await make_course(db, created_by=admin.id)
            await make_enrollment(
                db, user_id=partner.id, course_id=course.id, completed=i < done
            )
        await db.commit()
        return admin, company, partner

    async def test_measurement_matches_the_data(self, client, db):
        _, company, _ = await self._world(db, approved_opps=3, courses=4, done=3)
        opps, rate = await tier_service.measure_company(db, company.id)
        assert opps == 3
        assert rate == 75.0

    async def test_no_enrolments_is_zero_not_a_free_pass(self, client, db):
        # 0/0 must be 0%, not 100% — otherwise a company that has never opened
        # the LMS clears the training bar by doing nothing.
        _, company, _ = await self._world(db, approved_opps=1, courses=0, done=0)
        _, rate = await tier_service.measure_company(db, company.id)
        assert rate == 0.0

    async def test_dashboard_and_scorecard_report_the_same_progress(self, client, db):
        # The whole point. These are different endpoints, different services,
        # and used to be different rule sets.
        admin, company, partner = await self._world(
            db, approved_opps=5, courses=4, done=3
        )
        p_hdr = auth_header(partner)

        dash = await client.get("/api/v1/dashboard/partner/stats", headers=p_hdr)
        assert dash.status_code == 200, dash.text[:300]
        progress = dash.json()["tier_progress"]

        card = await client.get("/api/v1/scorecard/me", headers=p_hdr)
        assert card.status_code == 200, card.text[:300]

        assert progress["overall_progress_pct"] == card.json()["tier_progress_pct"]
        assert progress["next_tier"] == card.json()["next_tier"]

    async def test_the_dashboard_reports_the_real_thresholds(self, client, db):
        _, company, partner = await self._world(
            db, approved_opps=5, courses=4, done=3
        )
        dash = await client.get(
            "/api/v1/dashboard/partner/stats", headers=auth_header(partner)
        )
        progress = dash.json()["tier_progress"]
        # The numbers that actually promote — not the old 5-opps/3-courses.
        assert progress["opps_required"] == 10
        assert progress["lms_rate_required"] == 50.0
        assert progress["opps_current"] == 5
        assert progress["lms_rate_current"] == 75.0

    async def test_reaching_the_bar_promotes_and_the_screens_follow(self, client, db):
        admin, company, partner = await self._world(
            db, approved_opps=10, courses=2, done=1
        )
        # 10 approved opportunities and 50% completion — exactly the gold bar.
        change = await tier_service.review_company(db, company.id)
        assert change is not None and change.kind == "promoted"

        await db.commit()

        dash = await client.get(
            "/api/v1/dashboard/partner/stats", headers=auth_header(partner)
        )
        assert dash.json()["company_tier"] == "gold"
        # And the card now measures the distance to platinum, not to gold.
        assert dash.json()["tier_progress"]["next_tier"] == "platinum"
        assert dash.json()["tier_progress"]["opps_required"] == 20

    async def test_a_company_below_the_bar_is_not_promoted(self, client, db):
        _, company, _ = await self._world(db, approved_opps=10, courses=4, done=1)
        # 10 opportunities but only 25% completion. Already at silver, so
        # there is nothing to demote either.
        assert (await tier_service.review_company(db, company.id)) is None

    async def test_a_customer_company_is_never_promoted(self, client, db):
        from app.models.company import CompanyType

        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(
            db, channel_manager_id=admin.id, company_type=CompanyType.CUSTOMER
        )
        partner = await make_user(db, role=UserRole.PARTNER, company_id=company.id)
        for _ in range(25):
            await make_opportunity(
                db, company_id=company.id, submitted_by=partner.id,
                status=OpportunityStatus.APPROVED,
            )
        await db.commit()

        assert (await tier_service.review_company(db, company.id)) is None


# ---------------------------------------------------------------------------
# Reviews that can go downward
# ---------------------------------------------------------------------------

class TestDemotion:
    """Tier used to be a ratchet: a company that fell below its requirements
    kept the tier and the commission rate forever. Demotion is real now, and
    deliberately slow — the grace period is the difference between a warning
    with a deadline and an unannounced pay cut."""

    pytestmark = [requires_db, pytest.mark.asyncio]

    async def _gold_company(self, db, *, approved_opps: int, courses: int, done: int):
        """A company sitting at gold, whose current numbers you choose."""
        from app.models.company import PartnerTier

        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(db, channel_manager_id=admin.id)
        company.tier = PartnerTier.GOLD
        partner = await make_user(db, role=UserRole.PARTNER, company_id=company.id)
        for _ in range(approved_opps):
            await make_opportunity(
                db, company_id=company.id, submitted_by=partner.id,
                status=OpportunityStatus.APPROVED,
            )
        for i in range(courses):
            course = await make_course(db, created_by=admin.id)
            await make_enrollment(
                db, user_id=partner.id, course_id=course.id, completed=i < done
            )
        await db.commit()
        return admin, company, partner

    async def _reload(self, db, company_id):
        from sqlalchemy import select

        from app.models.company import Company

        row = (await db.execute(
            select(Company).where(Company.id == company_id)
        )).scalar_one()
        await db.refresh(row)
        return row

    async def test_falling_short_starts_a_grace_period_rather_than_demoting(
        self, client, db
    ):
        from app.models.company import PartnerTier

        _, company, _ = await self._gold_company(db, approved_opps=2, courses=2, done=1)
        change = await tier_service.review_company(db, company.id)
        await db.commit()

        assert change is not None and change.kind == "at_risk"
        row = await self._reload(db, company.id)
        assert row.tier == PartnerTier.GOLD, "the tier must not move on day one"
        assert row.tier_at_risk_since is not None

    async def test_the_warning_says_what_is_missing_and_by_when(self, client, db):
        # Short on both criteria — 2 of 10 opportunities, 25% of 50% training
        # — so the message has to name both rather than the first it finds.
        _, company, partner = await self._gold_company(
            db, approved_opps=2, courses=4, done=1
        )
        change = await tier_service.review_company(db, company.id)
        await db.commit()

        assert change.demote_on is not None
        notes = await client.get("/api/v1/notifications", headers=auth_header(partner))
        warning = next(
            n for n in notes.json()["items"] if n["type"] == "tier_at_risk"
        )
        # The shortfall is named on both criteria it fails.
        assert "approved opportunities" in warning["message"]
        assert "training completion" in warning["message"]

    async def test_the_clock_is_not_restarted_by_a_second_review(self, client, db):
        _, company, _ = await self._gold_company(db, approved_opps=2, courses=2, done=1)
        await tier_service.review_company(db, company.id)
        await db.commit()
        started = (await self._reload(db, company.id)).tier_at_risk_since

        assert (await tier_service.review_company(db, company.id)) is None
        await db.commit()
        assert (await self._reload(db, company.id)).tier_at_risk_since == started

    async def test_a_company_still_short_when_the_grace_runs_out_is_demoted(
        self, client, db
    ):
        from datetime import datetime, timedelta, timezone

        from app.core.config import settings
        from app.models.company import PartnerTier

        _, company, partner = await self._gold_company(
            db, approved_opps=2, courses=2, done=1
        )
        await tier_service.review_company(db, company.id)
        row = await self._reload(db, company.id)
        row.tier_at_risk_since = datetime.now(timezone.utc) - timedelta(
            days=settings.TIER_GRACE_DAYS + 1
        )
        await db.commit()

        change = await tier_service.review_company(db, company.id)
        await db.commit()
        assert change is not None and change.kind == "demoted"

        row = await self._reload(db, company.id)
        assert row.tier == PartnerTier.SILVER
        assert row.tier_at_risk_since is None

        notes = await client.get("/api/v1/notifications", headers=auth_header(partner))
        assert any(n["type"] == "tier_demoted" for n in notes.json()["items"])

    async def test_a_company_inside_the_grace_period_keeps_its_tier(self, client, db):
        from datetime import datetime, timedelta, timezone

        from app.core.config import settings
        from app.models.company import PartnerTier

        _, company, _ = await self._gold_company(db, approved_opps=2, courses=2, done=1)
        await tier_service.review_company(db, company.id)
        row = await self._reload(db, company.id)
        row.tier_at_risk_since = datetime.now(timezone.utc) - timedelta(
            days=settings.TIER_GRACE_DAYS - 1
        )
        await db.commit()

        assert (await tier_service.review_company(db, company.id)) is None
        assert (await self._reload(db, company.id)).tier == PartnerTier.GOLD

    async def test_recovering_inside_the_window_clears_it(self, client, db):
        from app.models.company import PartnerTier

        admin, company, partner = await self._gold_company(
            db, approved_opps=2, courses=2, done=1
        )
        await tier_service.review_company(db, company.id)
        await db.commit()
        assert (await self._reload(db, company.id)).tier_at_risk_since is not None

        # Back over the gold bar: 10 approved opportunities and 50% training.
        for _ in range(8):
            await make_opportunity(
                db, company_id=company.id, submitted_by=partner.id,
                status=OpportunityStatus.APPROVED,
            )
        await db.commit()

        change = await tier_service.review_company(db, company.id)
        await db.commit()
        assert change is not None and change.kind == "recovered"
        row = await self._reload(db, company.id)
        assert row.tier_at_risk_since is None
        assert row.tier == PartnerTier.GOLD

    async def test_a_promotion_clears_an_open_grace_period(self, client, db):
        # A company at risk on gold that vaults to platinum must not keep a
        # clock that would later demote it from the tier it just earned.
        from datetime import datetime, timezone

        from app.models.company import PartnerTier

        admin, company, partner = await self._gold_company(
            db, approved_opps=20, courses=5, done=4
        )
        row = await self._reload(db, company.id)
        row.tier_at_risk_since = datetime.now(timezone.utc)
        await db.commit()

        change = await tier_service.review_company(db, company.id)
        await db.commit()
        assert change.kind == "promoted"
        row = await self._reload(db, company.id)
        assert row.tier == PartnerTier.PLATINUM
        assert row.tier_at_risk_since is None

    async def test_a_customer_company_is_never_demoted(self, client, db):
        from app.models.company import CompanyType, PartnerTier

        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(
            db, channel_manager_id=admin.id, company_type=CompanyType.CUSTOMER
        )
        company.tier = PartnerTier.GOLD
        await db.commit()

        assert (await tier_service.review_company(db, company.id)) is None
        row = await self._reload(db, company.id)
        assert row.tier == PartnerTier.GOLD
        assert row.tier_at_risk_since is None

    async def test_the_sweep_reviews_every_channel_company(self, client, db):
        _, company, _ = await self._gold_company(db, approved_opps=2, courses=2, done=1)
        counts = await tier_service.sweep_tier_reviews(db)
        await db.commit()
        assert counts["at_risk"] >= 1
        assert (await self._reload(db, company.id)).tier_at_risk_since is not None


class TestTierHistory:
    """The record of why a tier moved. A demotion nobody can explain later is
    a support ticket; a demotion with its reason attached is an answer."""

    pytestmark = [requires_db, pytest.mark.asyncio]

    async def _promoted_company(self, db):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        company = await make_company(db, channel_manager_id=admin.id)
        partner = await make_user(db, role=UserRole.PARTNER, company_id=company.id)
        for _ in range(10):
            await make_opportunity(
                db, company_id=company.id, submitted_by=partner.id,
                status=OpportunityStatus.APPROVED,
            )
        for i in range(2):
            course = await make_course(db, created_by=admin.id)
            await make_enrollment(
                db, user_id=partner.id, course_id=course.id, completed=i < 1
            )
        await db.commit()
        await tier_service.review_company(db, company.id)
        await db.commit()
        return admin, company, partner

    async def test_a_promotion_is_recorded_with_its_reason(self, client, db):
        admin, company, partner = await self._promoted_company(db)
        r = await client.get(
            f"/api/v1/companies/{company.id}/tier-history", headers=auth_header(admin)
        )
        assert r.status_code == 200, r.text[:300]
        rows = r.json()
        assert rows[0]["new_tier"] == "gold"
        assert rows[0]["previous_tier"] == "silver"
        assert rows[0]["direction"] == "up"
        assert "approved opportunities" in rows[0]["reason"]

    async def test_a_partner_can_see_their_own_history(self, client, db):
        _, company, partner = await self._promoted_company(db)
        r = await client.get(
            f"/api/v1/companies/{company.id}/tier-history", headers=auth_header(partner)
        )
        assert r.status_code == 200, r.text[:300]
        assert len(r.json()) == 1

    async def test_a_partner_cannot_see_another_company_history(self, client, db):
        _, company, _ = await self._promoted_company(db)
        other_admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        other_company = await make_company(db, channel_manager_id=other_admin.id)
        outsider = await make_user(
            db, role=UserRole.PARTNER, company_id=other_company.id
        )
        await db.commit()

        r = await client.get(
            f"/api/v1/companies/{company.id}/tier-history",
            headers=auth_header(outsider),
        )
        assert r.status_code in (403, 404)

    async def test_an_out_of_scope_admin_cannot_see_it(self, client, db):
        _, company, _ = await self._promoted_company(db)
        other_admin = await make_user(db, role=UserRole.ADMIN)
        await db.commit()

        r = await client.get(
            f"/api/v1/companies/{company.id}/tier-history",
            headers=auth_header(other_admin),
        )
        assert r.status_code in (403, 404)

    async def test_a_demotion_is_recorded_as_downward(self, client, db):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.core.config import settings
        from app.models.company import Company

        admin, company, _ = await self._promoted_company(db)
        # Take the training rate below the gold bar by enrolling in more
        # courses without finishing them.
        for _ in range(4):
            course = await make_course(db, created_by=admin.id)
            await make_enrollment(
                db,
                user_id=(await make_user(
                    db, role=UserRole.PARTNER, company_id=company.id
                )).id,
                course_id=course.id,
                completed=False,
            )
        await db.commit()

        await tier_service.review_company(db, company.id)
        row = (await db.execute(
            select(Company).where(Company.id == company.id)
        )).scalar_one()
        row.tier_at_risk_since = datetime.now(timezone.utc) - timedelta(
            days=settings.TIER_GRACE_DAYS + 1
        )
        await db.commit()
        await tier_service.review_company(db, company.id)
        await db.commit()

        r = await client.get(
            f"/api/v1/companies/{company.id}/tier-history", headers=auth_header(admin)
        )
        newest = r.json()[0]
        assert newest["direction"] == "down"
        assert newest["previous_tier"] == "gold"
        assert "grace period" in newest["reason"]

    async def test_the_dashboard_shows_the_grace_deadline(self, client, db):
        _, company, partner = await self._promoted_company(db)
        for _ in range(4):
            course = await make_course(db, created_by=partner.id)
            await make_enrollment(
                db, user_id=partner.id, course_id=course.id, completed=False
            )
        await db.commit()
        await tier_service.review_company(db, company.id)
        await db.commit()

        dash = await client.get(
            "/api/v1/dashboard/partner/stats", headers=auth_header(partner)
        )
        progress = dash.json()["tier_progress"]
        assert progress["at_risk_until"] is not None
        assert "training completion" in progress["at_risk_shortfall"]
