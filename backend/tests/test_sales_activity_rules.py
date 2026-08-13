"""Unit tests for the pure business rules in sales_activity_service.

These need no DB: date validation and the modify-permission matrix are
plain functions over simple attributes.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestException, ForbiddenException
from app.models.user import UserRole
from app.services.sales_activity_service import (
    _assert_can_modify,
    _validate_activity_date,
    parse_month,
)


def _next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _last_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


class TestValidateActivityDate:
    def test_past_weekday_ok(self):
        _validate_activity_date(_last_weekday(date.today() - timedelta(days=7)))

    def test_weekend_rejected(self):
        d = date.today()
        while d.weekday() != 5:  # find a Saturday
            d -= timedelta(days=1)
        with pytest.raises(BadRequestException) as exc:
            _validate_activity_date(d)
        assert exc.value.code == "INVALID_ACTIVITY_DATE"

    def test_far_future_rejected(self):
        d = _next_weekday(date.today() + timedelta(days=30))
        with pytest.raises(BadRequestException) as exc:
            _validate_activity_date(d)
        assert exc.value.code == "INVALID_ACTIVITY_DATE"

    def test_one_day_of_timezone_slack(self):
        tomorrow = date.today() + timedelta(days=1)
        if tomorrow.weekday() < 5:
            _validate_activity_date(tomorrow)  # must not raise


def _user(id=1, role=UserRole.SALES_REP, superadmin=False):
    return SimpleNamespace(id=id, role=role, is_superadmin=superadmin)


def _activity(owner_id=1):
    return SimpleNamespace(user_id=owner_id)


class TestAssertCanModify:
    def test_rep_modifies_own(self):
        _assert_can_modify(_activity(owner_id=1), _user(id=1))

    def test_rep_cannot_modify_others(self):
        with pytest.raises(ForbiddenException, match="your own activities"):
            _assert_can_modify(_activity(owner_id=2), _user(id=1))

    def test_superadmin_modifies_anyones(self):
        _assert_can_modify(
            _activity(owner_id=2),
            _user(id=99, role=UserRole.ADMIN, superadmin=True),
        )

    def test_plain_admin_refused_with_accurate_message(self):
        with pytest.raises(ForbiddenException, match="Only superadmins"):
            _assert_can_modify(_activity(owner_id=2), _user(id=99, role=UserRole.ADMIN))

    def test_partner_refused(self):
        with pytest.raises(ForbiddenException, match="Only superadmins"):
            _assert_can_modify(_activity(owner_id=2), _user(id=3, role=UserRole.PARTNER))


class TestParseMonth:
    def test_valid(self):
        first, last = parse_month("2026-02")
        assert first == date(2026, 2, 1)
        assert last == date(2026, 2, 28)

    @pytest.mark.parametrize("bad", ["2026-13", "2026-0", "202602", "", "abcd-ef"])
    def test_invalid(self, bad):
        with pytest.raises(BadRequestException):
            parse_month(bad)
