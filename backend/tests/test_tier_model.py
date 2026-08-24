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
        from app.services.dashboard_service import evaluate_tier_upgrade

        admin, company, partner = await self._world(
            db, approved_opps=10, courses=2, done=1
        )
        # 10 approved opportunities and 50% completion — exactly the gold bar.
        assert (await evaluate_tier_upgrade(db, company.id)) is not None
        await db.commit()

        dash = await client.get(
            "/api/v1/dashboard/partner/stats", headers=auth_header(partner)
        )
        assert dash.json()["company_tier"] == "gold"
        # And the card now measures the distance to platinum, not to gold.
        assert dash.json()["tier_progress"]["next_tier"] == "platinum"
        assert dash.json()["tier_progress"]["opps_required"] == 20

    async def test_a_company_below_the_bar_is_not_promoted(self, client, db):
        from app.services.dashboard_service import evaluate_tier_upgrade

        _, company, _ = await self._world(db, approved_opps=10, courses=4, done=1)
        # 10 opportunities but only 25% completion.
        assert (await evaluate_tier_upgrade(db, company.id)) is None

    async def test_a_customer_company_is_never_promoted(self, client, db):
        from app.models.company import CompanyType
        from app.services.dashboard_service import evaluate_tier_upgrade

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

        assert (await evaluate_tier_upgrade(db, company.id)) is None
