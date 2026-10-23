"""Unit tests for status computation and overdue rules."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.status import compute_status, is_active_overdue


@pytest.mark.parametrize(
    "due_date,today,expected",
    [
        # unpaid before the deadline
        (date(2026, 10, 10), date(2026, 10, 1), "pending"),
        # exactly on the deadline -> NOT overdue
        (date(2026, 10, 10), date(2026, 10, 10), "due_soon"),
        # the day after the deadline -> overdue
        (date(2026, 10, 10), date(2026, 10, 11), "overdue"),
        # far in the future
        (date(2026, 12, 31), date(2026, 10, 1), "pending"),
    ],
)
def test_unpaid_statuses(due_date, today, expected):
    assert (
        compute_status(is_paid=False, paid_at=None, due_date=due_date, today=today)
        == expected
    )


def test_due_soon_window_uses_reminder_setting():
    due = date(2026, 10, 10)
    assert compute_status(is_paid=False, paid_at=None, due_date=due, today=date(2026, 10, 7)) == "due_soon"
    assert compute_status(is_paid=False, paid_at=None, due_date=due, today=date(2026, 10, 6)) == "pending"


def test_paid_on_time_and_late():
    due = date(2026, 10, 10)
    assert compute_status(is_paid=True, paid_at=date(2026, 10, 10), due_date=due) == "paid_on_time"
    assert compute_status(is_paid=True, paid_at=date(2026, 10, 9), due_date=due) == "paid_on_time"
    assert compute_status(is_paid=True, paid_at=date(2026, 10, 12), due_date=due) == "paid_late"


def test_late_payment_is_not_reported_as_overdue():
    """A period paid late must never show as still unpaid/overdue."""
    due = date(2026, 10, 10)
    status = compute_status(
        is_paid=True, paid_at=date(2026, 10, 20), due_date=due, today=date(2026, 11, 1)
    )
    assert status == "paid_late"
    assert is_active_overdue(True, due, date(2026, 11, 1)) is False


def test_overdue_formula_is_strictly_greater_than_due_date():
    due = date(2026, 10, 10)
    assert is_active_overdue(False, due, date(2026, 10, 10)) is False
    assert is_active_overdue(False, due, date(2026, 10, 11)) is True
    assert is_active_overdue(True, due, date(2026, 10, 11)) is False
