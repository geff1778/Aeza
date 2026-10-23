"""Analytics: dashboard, payments summary and calendar."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import occurrence_out
from app.config import settings
from app.db import get_db
from app.models import (
    AuditLog,
    Currency,
    PaymentOccurrence,
    RecurringPayment,
    User,
)
from app.schemas import (
    AuditOut,
    CalendarDay,
    CalendarOut,
    CurrencyTotals,
    DashboardOut,
    IntegrationStatus,
    OccurrenceOut,
    SummaryOut,
)
from app.services.dates import local_today
from app.services.status import compute_status

router = APIRouter(tags=["analytics"])

ZERO = Decimal("0")


def _all_rows(db: Session) -> list[tuple[PaymentOccurrence, RecurringPayment]]:
    return db.execute(
        select(PaymentOccurrence, RecurringPayment).join(
            RecurringPayment, PaymentOccurrence.recurring_payment_id == RecurringPayment.id
        )
    ).all()


def _empty_totals(currency: Currency) -> dict:
    return {"currency": currency, "upcoming": ZERO, "overdue": ZERO, "paid": ZERO}


def _aggregate(rows, today: date) -> list[CurrencyTotals]:
    """Aggregate per currency — different currencies are never summed together."""
    buckets: dict[Currency, dict] = {c: _empty_totals(c) for c in Currency}
    for occurrence, _payment in rows:
        bucket = buckets[occurrence.currency]
        if occurrence.is_paid:
            bucket["paid"] += occurrence.amount
        elif occurrence.due_date < today:
            bucket["overdue"] += occurrence.amount
        else:
            bucket["upcoming"] += occurrence.amount
    return [CurrencyTotals(**buckets[c]) for c in Currency]


@router.get("/payments/summary", response_model=SummaryOut)
def payments_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SummaryOut:
    today = local_today(settings.tz)
    rows = _all_rows(db)

    status_counts = {
        "paid_on_time": 0,
        "paid_late": 0,
        "overdue": 0,
        "due_soon": 0,
        "pending": 0,
    }
    by_month: dict[str, dict] = {}
    for occurrence, _payment in rows:
        status_value = compute_status(
            is_paid=occurrence.is_paid, paid_at=occurrence.paid_at, due_date=occurrence.due_date, today=today
        )
        status_counts[status_value] += 1

        key = occurrence.due_date.strftime("%Y-%m")
        entry = by_month.setdefault(
            key,
            {
                "month": key,
                "currencies": {
                    c.value: {"planned": "0", "paid": "0", "overdue": "0"} for c in Currency
                },
            },
        )
        cur = entry["currencies"][occurrence.currency.value]
        cur["planned"] = str(Decimal(cur["planned"]) + occurrence.amount)
        if occurrence.is_paid:
            cur["paid"] = str(Decimal(cur["paid"]) + occurrence.amount)
        elif occurrence.due_date < today:
            cur["overdue"] = str(Decimal(cur["overdue"]) + occurrence.amount)

    return SummaryOut(
        today=today,
        timezone=settings.APP_TIMEZONE,
        by_currency=_aggregate(rows, today),
        by_month=[by_month[k] for k in sorted(by_month)],
        status_counts=status_counts,
        overdue_count=status_counts["overdue"],
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardOut:
    today = local_today(settings.tz)
    rows = _all_rows(db)

    due_soon = overdue = paid_count = 0
    upcoming: list[OccurrenceOut] = []
    for occurrence, payment in rows:
        status_value = compute_status(
            is_paid=occurrence.is_paid, paid_at=occurrence.paid_at, due_date=occurrence.due_date, today=today
        )
        if status_value == "overdue":
            overdue += 1
        elif status_value == "due_soon":
            due_soon += 1
        elif status_value in ("paid_on_time", "paid_late"):
            if occurrence.due_date >= today.replace(day=1):
                paid_count += 1
        if not occurrence.is_paid and occurrence.due_date >= today - timedelta(days=30):
            upcoming.append(occurrence_out(occurrence, payment, today=today))

    upcoming.sort(key=lambda o: o.due_date)
    recent = list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8))
    )

    integrations = IntegrationStatus(
        telegram_configured=settings.telegram_enabled,
        telegram_hint=None if settings.telegram_enabled else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы",
        smtp_configured=settings.smtp_enabled,
        smtp_hint=None if settings.smtp_enabled else "SMTP_HOST / SMTP_FROM не заданы",
    )

    return DashboardOut(
        today=today,
        timezone=settings.APP_TIMEZONE,
        totals=_aggregate(rows, today),
        due_soon_count=due_soon,
        overdue_count=overdue,
        paid_count=paid_count,
        upcoming=upcoming[:12],
        recent_activity=[AuditOut.model_validate(a) for a in recent],
        integrations=integrations.model_dump(),
    )


@router.get("/calendar", response_model=CalendarOut)
def calendar(
    month: str = Query(description="Формат YYYY-MM"),
    currency: Currency | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CalendarOut:
    try:
        year, mon = (int(x) for x in month.split("-"))
        start = date(year, mon, 1)
    except Exception as exc:  # noqa: BLE001
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month должен быть в формате YYYY-MM",
        ) from exc

    end = date(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1) - timedelta(days=1)
    today = local_today(settings.tz)

    stmt = (
        select(PaymentOccurrence, RecurringPayment)
        .join(RecurringPayment, PaymentOccurrence.recurring_payment_id == RecurringPayment.id)
        .where(PaymentOccurrence.due_date >= start, PaymentOccurrence.due_date <= end)
        .order_by(PaymentOccurrence.due_date)
    )
    if currency is not None:
        stmt = stmt.where(PaymentOccurrence.currency == currency)

    days: dict[date, list[OccurrenceOut]] = {}
    for occurrence, payment in db.execute(stmt).all():
        item = occurrence_out(occurrence, payment, today=today)
        if status_filter and item.status != status_filter:
            continue
        days.setdefault(occurrence.due_date, []).append(item)

    return CalendarOut(
        month=month,
        days=[CalendarDay(date=d, items=days[d]) for d in sorted(days)],
    )
