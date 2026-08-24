"""Unit tests for the distributor → reseller hierarchy.

Two things are pinned here, and they are the two that decide who can read
whose pipeline:

  1. The shape rules (company_service.assert_valid_parent_distributor and
     assert_can_change_type) — only a partner may have a parent, only a
     distributor may be one, and a link may not be stranded by a later
     reclassification. Together these make a cycle unreachable, which is why
     nothing walks the graph looking for one.

  2. The scope resolver (deps.get_partner_pipeline_scope) — a distributor's
     scope contains its resellers; a reseller's contains only itself, never a
     sibling and never the parent. Visibility walks downward only.

These run without a database: the queries are stubbed, so the rules stay
covered on a developer machine with no Postgres. The end-to-end version
(a real distributor user getting a real reseller's opportunity over HTTP)
lives in test_rbac_visibility.py.
"""
import pytest

from app.core.deps import get_partner_pipeline_scope
from app.core.exceptions import BadRequestException, ConflictException
from app.models.company import Company, CompanyType
from app.models.user import User, UserRole
from app.services.company_service import (
    assert_can_change_type,
    assert_valid_parent_distributor,
)


class FakeResult:
    """Stands in for the object db.execute() returns, for the two shapes the
    code under test uses: .scalar_one_or_none() and .all()."""

    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeDb:
    """Returns queued results in order, one per execute() call."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        if not self._results:
            return FakeResult([])
        return self._results.pop(0)


def company(id_, type_, parent_id=None):
    c = Company()
    c.id = id_
    c.company_type = type_
    c.parent_distributor_id = parent_id
    c.name = f"Company {id_}"
    return c


def partner_user(id_, company_obj):
    u = User()
    u.id = id_
    u.role = UserRole.PARTNER
    u.company_id = company_obj.id if company_obj else None
    u.company = company_obj
    return u


# ---------------------------------------------------------------------------
# assert_valid_parent_distributor
# ---------------------------------------------------------------------------

class TestParentDistributorRules:
    @pytest.mark.asyncio
    async def test_no_parent_is_always_valid(self):
        db = FakeDb()
        result = await assert_valid_parent_distributor(
            db, child_type=CompanyType.PARTNER, parent_distributor_id=None
        )
        assert result is None
        # It must not have gone looking for a row that isn't referenced.
        assert db.calls == 0

    @pytest.mark.asyncio
    async def test_partner_under_distributor_is_valid(self):
        parent = company(10, CompanyType.DISTRIBUTOR)
        db = FakeDb(FakeResult([parent]))
        assert (
            await assert_valid_parent_distributor(
                db, child_type=CompanyType.PARTNER, parent_distributor_id=10
            )
            is parent
        )

    @pytest.mark.asyncio
    async def test_distributor_cannot_have_a_parent(self):
        # This is the rule that makes the graph two levels deep: a parent can
        # never itself be a child, so no cycle is constructible.
        db = FakeDb(FakeResult([company(10, CompanyType.DISTRIBUTOR)]))
        with pytest.raises(BadRequestException):
            await assert_valid_parent_distributor(
                db, child_type=CompanyType.DISTRIBUTOR, parent_distributor_id=10
            )

    @pytest.mark.asyncio
    async def test_customer_cannot_have_a_parent(self):
        db = FakeDb(FakeResult([company(10, CompanyType.DISTRIBUTOR)]))
        with pytest.raises(BadRequestException):
            await assert_valid_parent_distributor(
                db, child_type=CompanyType.CUSTOMER, parent_distributor_id=10
            )

    @pytest.mark.asyncio
    async def test_parent_must_be_a_distributor(self):
        db = FakeDb(FakeResult([company(10, CompanyType.PARTNER)]))
        with pytest.raises(BadRequestException):
            await assert_valid_parent_distributor(
                db, child_type=CompanyType.PARTNER, parent_distributor_id=10
            )

    @pytest.mark.asyncio
    async def test_parent_must_exist(self):
        db = FakeDb(FakeResult([]))
        with pytest.raises(BadRequestException):
            await assert_valid_parent_distributor(
                db, child_type=CompanyType.PARTNER, parent_distributor_id=999
            )

    @pytest.mark.asyncio
    async def test_company_cannot_be_its_own_parent(self):
        db = FakeDb(FakeResult([company(7, CompanyType.DISTRIBUTOR)]))
        with pytest.raises(BadRequestException):
            await assert_valid_parent_distributor(
                db,
                child_type=CompanyType.PARTNER,
                parent_distributor_id=7,
                child_company_id=7,
            )


# ---------------------------------------------------------------------------
# assert_can_change_type
# ---------------------------------------------------------------------------

class TestTypeChangeRules:
    @pytest.mark.asyncio
    async def test_same_type_is_a_no_op(self):
        db = FakeDb()
        await assert_can_change_type(
            db, company(1, CompanyType.DISTRIBUTOR), CompanyType.DISTRIBUTOR
        )
        assert db.calls == 0

    @pytest.mark.asyncio
    async def test_distributor_with_resellers_cannot_be_reclassified(self):
        db = FakeDb(FakeResult([3]))  # three resellers underneath
        with pytest.raises(ConflictException):
            await assert_can_change_type(
                db, company(1, CompanyType.DISTRIBUTOR), CompanyType.PARTNER
            )

    @pytest.mark.asyncio
    async def test_distributor_without_resellers_can_be_reclassified(self):
        db = FakeDb(FakeResult([0]))
        await assert_can_change_type(
            db, company(1, CompanyType.DISTRIBUTOR), CompanyType.PARTNER
        )

    @pytest.mark.asyncio
    async def test_reseller_cannot_become_a_customer(self):
        # It would keep a parent_distributor_id that the shape rules forbid.
        db = FakeDb()
        with pytest.raises(ConflictException):
            await assert_can_change_type(
                db,
                company(2, CompanyType.PARTNER, parent_id=1),
                CompanyType.CUSTOMER,
            )

    @pytest.mark.asyncio
    async def test_reseller_cannot_become_a_distributor(self):
        db = FakeDb()
        with pytest.raises(ConflictException):
            await assert_can_change_type(
                db,
                company(2, CompanyType.PARTNER, parent_id=1),
                CompanyType.DISTRIBUTOR,
            )

    @pytest.mark.asyncio
    async def test_unlinked_partner_can_become_a_customer(self):
        db = FakeDb()
        await assert_can_change_type(
            db, company(2, CompanyType.PARTNER), CompanyType.CUSTOMER
        )


# ---------------------------------------------------------------------------
# get_partner_pipeline_scope
# ---------------------------------------------------------------------------

class TestPipelineScope:
    @pytest.mark.asyncio
    async def test_distributor_sees_itself_and_its_resellers(self):
        distributor = company(1, CompanyType.DISTRIBUTOR)
        db = FakeDb(FakeResult([(2,), (3,)]))
        scope = await get_partner_pipeline_scope(db, partner_user(100, distributor))
        assert scope == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_reseller_sees_only_itself(self):
        # The crux of the requirement: resellers must not see one another.
        # A reseller is a PARTNER, so can_have_resellers is False and the
        # scope never widens — no sibling, and no parent either.
        reseller = company(2, CompanyType.PARTNER, parent_id=1)
        db = FakeDb()
        scope = await get_partner_pipeline_scope(db, partner_user(200, reseller))
        assert scope == [2]
        assert db.calls == 0

    @pytest.mark.asyncio
    async def test_scope_never_contains_the_parent(self):
        reseller = company(2, CompanyType.PARTNER, parent_id=1)
        scope = await get_partner_pipeline_scope(FakeDb(), partner_user(200, reseller))
        assert 1 not in scope

    @pytest.mark.asyncio
    async def test_plain_partner_sees_only_itself(self):
        plain = company(5, CompanyType.PARTNER)
        scope = await get_partner_pipeline_scope(FakeDb(), partner_user(300, plain))
        assert scope == [5]

    @pytest.mark.asyncio
    async def test_customer_company_still_gets_its_own_pipeline(self):
        # A customer is outside the partner programme but still tracks its own
        # opportunities, POCs and licences.
        cust = company(6, CompanyType.CUSTOMER)
        scope = await get_partner_pipeline_scope(FakeDb(), partner_user(400, cust))
        assert scope == [6]

    @pytest.mark.asyncio
    async def test_user_without_a_company_sees_nothing(self):
        # `[]` must mean no rows. Every caller filters with `IN (scope)`, so an
        # empty scope matches nothing — the failure mode to avoid is a caller
        # treating it as "unscoped".
        scope = await get_partner_pipeline_scope(FakeDb(), partner_user(500, None))
        assert scope == []

    @pytest.mark.asyncio
    async def test_distributor_with_no_resellers_sees_only_itself(self):
        distributor = company(1, CompanyType.DISTRIBUTOR)
        db = FakeDb(FakeResult([]))
        scope = await get_partner_pipeline_scope(db, partner_user(100, distributor))
        assert scope == [1]
