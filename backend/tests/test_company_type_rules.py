"""Unit tests for the company-type capability rules.

These are the pure predicates that decide whether a company takes part in the
partner programme — deal registration, commissions, scorecards and tier
progression. They need no database: everything under test reads plain
attributes off a company or a user.
"""
from types import SimpleNamespace

import pytest

from app.core.deps import is_customer_company_user
from app.models.company import (
    CHANNEL_COMPANY_TYPES,
    Company,
    CompanyType,
    PartnerTier,
)
from app.models.user import UserRole
from app.schemas.company import COMPANY_TYPE_PATTERN
from app.services.company_service import tier_for


def _company(company_type: CompanyType, tier: PartnerTier = PartnerTier.GOLD) -> Company:
    """A Company instance with only the fields these rules read. Not added to
    a session — is_channel_partner and tier_for are pure."""
    return Company(company_type=company_type, tier=tier)


class TestCompanyTypeEnum:
    def test_exactly_three_types(self):
        assert {t.value for t in CompanyType} == {"customer", "distributor", "partner"}

    def test_partner_and_distributor_are_channel_types(self):
        assert CompanyType.PARTNER in CHANNEL_COMPANY_TYPES
        assert CompanyType.DISTRIBUTOR in CHANNEL_COMPANY_TYPES

    def test_customer_is_not_a_channel_type(self):
        assert CompanyType.CUSTOMER not in CHANNEL_COMPANY_TYPES

    def test_schema_pattern_accepts_every_enum_value(self):
        import re

        for t in CompanyType:
            assert re.match(COMPANY_TYPE_PATTERN, t.value), t.value

    def test_schema_pattern_rejects_unknown(self):
        import re

        for bad in ("reseller", "Partner", "", "customer ", "partner;drop"):
            assert re.match(COMPANY_TYPE_PATTERN, bad) is None, bad


class TestIsChannelPartner:
    @pytest.mark.parametrize(
        "company_type,expected",
        [
            (CompanyType.PARTNER, True),
            (CompanyType.DISTRIBUTOR, True),
            (CompanyType.CUSTOMER, False),
        ],
    )
    def test_membership(self, company_type, expected):
        assert _company(company_type).is_channel_partner is expected


class TestTierFor:
    def test_partner_keeps_its_tier(self):
        assert tier_for(_company(CompanyType.PARTNER, PartnerTier.PLATINUM)) == "platinum"

    def test_distributor_keeps_its_tier(self):
        assert tier_for(_company(CompanyType.DISTRIBUTOR, PartnerTier.SILVER)) == "silver"

    def test_customer_tier_is_nulled_out(self):
        # The column is NOT NULL and still holds a value; reads must not leak
        # a meaningless tier onto a customer.
        company = _company(CompanyType.CUSTOMER, PartnerTier.GOLD)
        assert company.tier == PartnerTier.GOLD
        assert tier_for(company) is None


class TestIsCustomerCompanyUser:
    def _user(self, role, company):
        return SimpleNamespace(role=role, company=company)

    def test_partner_at_customer_company_is_a_customer_user(self):
        user = self._user(UserRole.PARTNER, _company(CompanyType.CUSTOMER))
        assert is_customer_company_user(user) is True

    @pytest.mark.parametrize(
        "company_type", [CompanyType.PARTNER, CompanyType.DISTRIBUTOR]
    )
    def test_partner_at_channel_company_is_not(self, company_type):
        user = self._user(UserRole.PARTNER, _company(company_type))
        assert is_customer_company_user(user) is False

    def test_admin_has_no_company_and_is_never_a_customer_user(self):
        # Admins and superadmins run the programme rather than take part in
        # it, so they must never be caught by the customer guard.
        assert is_customer_company_user(self._user(UserRole.ADMIN, None)) is False

    def test_sales_rep_has_no_company_and_is_never_a_customer_user(self):
        assert is_customer_company_user(self._user(UserRole.SALES_REP, None)) is False
