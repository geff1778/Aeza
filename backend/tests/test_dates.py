"""Unit tests for calendar arithmetic: no date drift, month ends, leap years."""
from __future__ import annotations

from datetime import date

import pytest

from app.models import Recurrence
from app.services.dates import (
    add_months_anchored,
    clamp_day,
    iter_due_dates,
    nth_due_date,
    reminder_date,
)


@pytest.mark.parametrize(
    "year,month,day,expected",
    [
        (2026, 2, 31, date(2026, 2, 28)),
        (2024, 2, 31, date(2024, 2, 29)),  # leap year
        (2026, 4, 31, date(2026, 4, 30)),
        (2026, 1, 31, date(2026, 1, 31)),
        (2026, 12, 31, date(2026, 12, 31)),
    ],
)
def test_clamp_day(year, month, day, expected):
    assert clamp_day(year, month, day) == expected


def test_month_end_sequence_does_not_drift():
    """31 Jan -> 28 Feb -> 31 Mar (anchor day preserved, no permanent drift)."""
    first = date(2026, 1, 31)
    assert nth_due_date(first, Recurrence.monthly, 31, 0) == date(2026, 1, 31)
    assert nth_due_date(first, Recurrence.monthly, 31, 1) == date(2026, 2, 28)
    assert nth_due_date(first, Recurrence.monthly, 31, 2) == date(2026, 3, 31)
    assert nth_due_date(first, Recurrence.monthly, 31, 3) == date(2026, 4, 30)
    assert nth_due_date(first, Recurrence.monthly, 31, 4) == date(2026, 5, 31)


def test_leap_year_february_29_anchor():
    first = date(2024, 1, 29)
    assert nth_due_date(first, Recurrence.monthly, 29, 1) == date(2024, 2, 29)
    assert nth_due_date(first, Recurrence.monthly, 29, 2) == date(2024, 3, 29)
    # non-leap year clamps to 28
    assert nth_due_date(date(2026, 1, 29), Recurrence.monthly, 29, 1) == date(2026, 2, 28)


def test_month_boundary_crossing():
    assert nth_due_date(date(2026, 11, 15), Recurrence.monthly, 15, 2) == date(2027, 1, 15)
    assert nth_due_date(date(2026, 12, 5), Recurrence.monthly, 5, 1) == date(2027, 1, 5)


def test_anchor_day_28_30_31():
    for day in (28, 30, 31):
        first = date(2026, 1, day)
        second = nth_due_date(first, Recurrence.monthly, day, 1)
        assert second == clamp_day(2026, 2, day)


def test_quarterly_and_yearly():
    first = date(2026, 1, 15)
    assert nth_due_date(first, Recurrence.quarterly, 15, 1) == date(2026, 4, 15)
    assert nth_due_date(first, Recurrence.yearly, 15, 1) == date(2027, 1, 15)


def test_iter_due_dates_respects_horizon():
    dates = iter_due_dates(date(2026, 1, 10), Recurrence.monthly, 10, date(2026, 3, 31))
    assert dates == [date(2026, 1, 10), date(2026, 2, 10), date(2026, 3, 10)]


def test_reminder_date_three_days_before():
    assert reminder_date(date(2026, 10, 26), 3) == date(2026, 10, 23)


def test_add_months_anchored_wraps_years():
    assert add_months_anchored(2026, 11, 3, 30) == date(2027, 2, 28)
    assert add_months_anchored(2026, 1, 12, 1) == date(2027, 1, 1)
