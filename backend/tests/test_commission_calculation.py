"""
Unit tests for commission calculation logic.

These tests focus on the PURE math + state-machine parts of
commission_service — quantization, tier rate lookup, and the
state-transition table — so they run without any DB or network.
"""
from decimal import Decimal

import pytest

from app.models.commission import CommissionStatus
from app.models.company import PartnerTier
from app.services.commission_service import (
    TIER_THRESHOLDS,
    VALID_TRANSITIONS,
    _next_tier,
    _quantize,
    _tier_progress_pct,
)


class TestQuantize:
    def test_two_decimal_places(self):
        assert _quantize(Decimal("123.456")) == Decimal("123.46")

    def test_round_half_even(self):
        # Banker's rounding: 0.125 -> 0.12 (not 0.13)
        assert _quantize(Decimal("0.125")) == Decimal("0.12")
        # 0.135 -> 0.14 (rounds to even)
        assert _quantize(Decimal("0.135")) == Decimal("0.14")

    def test_no_change_for_already_quantized(self):
        assert _quantize(Decimal("5.00")) == Decimal("5.00")

    def test_zero(self):
        assert _quantize(Decimal("0")) == Decimal("0.00")


class TestTierProgression:
    def test_next_tier_from_silver(self):
        assert _next_tier(PartnerTier.SILVER) == PartnerTier.GOLD

    def test_next_tier_from_gold(self):
        assert _next_tier(PartnerTier.GOLD) == PartnerTier.PLATINUM

    def test_next_tier_from_platinum_is_none(self):
        assert _next_tier(PartnerTier.PLATINUM) is None

    def test_progress_pct_at_zero(self):
        assert _tier_progress_pct(PartnerTier.SILVER, 0) == 0.0

    def test_progress_pct_halfway(self):
        threshold = TIER_THRESHOLDS[PartnerTier.GOLD]
        half = threshold // 2
        expected = (half / threshold) * 100
        assert _tier_progress_pct(PartnerTier.SILVER, half) == pytest.approx(expected)

    def test_progress_pct_capped_at_100(self):
        # Overshooting the threshold shouldn't go beyond 100
        threshold = TIER_THRESHOLDS[PartnerTier.GOLD]
        assert _tier_progress_pct(PartnerTier.SILVER, threshold * 10) == 100.0

    def test_progress_pct_platinum_is_max(self):
        # Platinum has no higher tier, always 100%
        assert _tier_progress_pct(PartnerTier.PLATINUM, 0) == 100.0
        assert _tier_progress_pct(PartnerTier.PLATINUM, 999) == 100.0


class TestStatusStateMachine:
    def test_pending_can_approve(self):
        assert CommissionStatus.APPROVED in VALID_TRANSITIONS[CommissionStatus.PENDING]

    def test_pending_can_void(self):
        assert CommissionStatus.VOID in VALID_TRANSITIONS[CommissionStatus.PENDING]

    def test_approved_can_pay(self):
        assert CommissionStatus.PAID in VALID_TRANSITIONS[CommissionStatus.APPROVED]

    def test_approved_can_void(self):
        assert CommissionStatus.VOID in VALID_TRANSITIONS[CommissionStatus.APPROVED]

    def test_paid_is_terminal(self):
        assert VALID_TRANSITIONS[CommissionStatus.PAID] == set()

    def test_void_is_terminal(self):
        assert VALID_TRANSITIONS[CommissionStatus.VOID] == set()

    def test_cannot_skip_approval_to_paid(self):
        # Must go pending -> approved -> paid
        assert CommissionStatus.PAID not in VALID_TRANSITIONS[CommissionStatus.PENDING]


class TestCommissionMath:
    """Verify the underlying math would produce correct amounts for each tier."""

    def test_silver_5pct(self):
        deal_value = Decimal("10000")
        rate = Decimal("5.00")
        amount = _quantize(deal_value * rate / Decimal("100"))
        assert amount == Decimal("500.00")

    def test_gold_8pct(self):
        deal_value = Decimal("10000")
        rate = Decimal("8.00")
        amount = _quantize(deal_value * rate / Decimal("100"))
        assert amount == Decimal("800.00")

    def test_platinum_12pct(self):
        deal_value = Decimal("10000")
        rate = Decimal("12.00")
        amount = _quantize(deal_value * rate / Decimal("100"))
        assert amount == Decimal("1200.00")

    def test_odd_values_quantize_correctly(self):
        deal_value = Decimal("12345.67")
        rate = Decimal("8.00")
        amount = _quantize(deal_value * rate / Decimal("100"))
        # 12345.67 * 0.08 = 987.6536
        assert amount == Decimal("987.65")
