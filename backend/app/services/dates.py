"""Pure calendar arithmetic for recurring payments.

All recurrence rules are anchored to the *original* day of the month so a short
month (e.g. February) never causes a permanent drift of future due dates.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import Recurrence

_MONTHS_PER_INTERVAL = {
    Recurrence.monthly: 1,
    Recurrence.quarterly: 3,
    Recurrence.yearly: 12,
}


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, last_day_of_month(year, month)))


def add_months_anchored(
    base_year: int, base_month: int, months: int, anchor_day: int
) -> date:
    total = (base_month - 1) + months
    year = base_year + total // 12
    month = total % 12 + 1
    return clamp_day(year, month, anchor_day)


def nth_due_date(
    first_due_date: date, recurrence: Recurrence, anchor_day: int, index: int
) -> date:
    """Return the due date of occurrence ``index`` (0 == first period).

    Computed from the anchor rather than by repeatedly adding a month, so
    31 Jan -> 28 Feb -> 31 Mar (no drift).
    """
    step = _MONTHS_PER_INTERVAL[recurrence]
    return add_months_anchored(
        first_due_date.year, first_due_date.month, step * index, anchor_day
    )


def iter_due_dates(
    first_due_date: date,
    recurrence: Recurrence,
    anchor_day: int,
    until: date,
    max_count: int = 600,
) -> list[date]:
    """All due dates from the first period up to and including ``until``."""
    result: list[date] = []
    index = 0
    while index < max_count:
        current = nth_due_date(first_due_date, recurrence, anchor_day, index)
        if current > until:
            break
        result.append(current)
        index += 1
    return result


def local_today(tz: ZoneInfo, now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(tz).date()


def days_until(due_date: date, today: date) -> int:
    return (due_date - today).days


def reminder_date(due_date: date, days_before: int) -> date:
    return due_date - timedelta(days=days_before)
