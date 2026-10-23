"""Budgets per period type and currency. Read for everyone, write for admins."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, verify_csrf
from app.config import settings
from app.db import get_db
from app.models import Budget, BudgetPeriod, Currency, PaymentOccurrence, User
from app.schemas import BudgetOut, BudgetUpsert
from app.services import audit
from app.services.dates import local_today

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _period_bounds(period_type: BudgetPeriod, period_key: str) -> tuple[date, date]:
    if period_type == BudgetPeriod.month:
        year, month = (int(x) for x in period_key.split("-"))
        start = date(year, month, 1)
        end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        return start, end
    year = int(period_key)
    return date(year, 1, 1), date(year + 1, 1, 1)


def _compute(db: Session, budget: Budget, today: date) -> BudgetOut:
    start, end = _period_bounds(budget.period_type, budget.period_key)
    rows = list(
        db.scalars(
            select(PaymentOccurrence).where(
                PaymentOccurrence.currency == budget.currency,
                PaymentOccurrence.due_date >= start,
                PaymentOccurrence.due_date < end,
            )
        )
    )
    # planned = every scheduled period in range (forecast); actual = paid only.
    planned = sum((o.amount for o in rows), Decimal("0"))
    actual = sum((o.amount for o in rows if o.is_paid), Decimal("0"))
    # The budget is a spending cap, so the forecast (planned) drives the
    # warning state and the usage percentage.
    remaining = budget.limit_amount - planned
    usage = float(planned / budget.limit_amount * 100) if budget.limit_amount > 0 else 0.0
    return BudgetOut(
        id=budget.id,
        period_type=budget.period_type,
        period_key=budget.period_key,
        currency=budget.currency,
        limit_amount=budget.limit_amount,
        planned_amount=planned,
        actual_amount=actual,
        remaining=remaining,
        usage_percent=round(usage, 2),
        over_limit=planned > budget.limit_amount,
    )


@router.get("", response_model=list[BudgetOut])
def list_budgets(
    period_type: BudgetPeriod | None = None,
    period_key: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[BudgetOut]:
    stmt = select(Budget)
    if period_type is not None:
        stmt = stmt.where(Budget.period_type == period_type)
    if period_key is not None:
        stmt = stmt.where(Budget.period_key == period_key)
    stmt = stmt.order_by(Budget.period_type, Budget.period_key, Budget.currency)
    today = local_today(settings.tz)
    return [_compute(db, b, today) for b in db.scalars(stmt)]


@router.put("", response_model=BudgetOut)
def upsert_budget(
    payload: BudgetUpsert,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> BudgetOut:
    _period_bounds(payload.period_type, payload.period_key)  # validate the key format
    budget = db.scalar(
        select(Budget).where(
            Budget.period_type == payload.period_type,
            Budget.period_key == payload.period_key,
            Budget.currency == payload.currency,
        )
    )
    if budget is None:
        budget = Budget(
            period_type=payload.period_type,
            period_key=payload.period_key,
            currency=payload.currency,
            limit_amount=payload.limit_amount,
        )
        db.add(budget)
        action = "budget.created"
        old = None
    else:
        old = str(budget.limit_amount)
        budget.limit_amount = payload.limit_amount
        action = "budget.updated"

    db.flush()
    audit.record(
        db,
        action=action,
        entity_type="budget",
        entity_id=budget.id,
        description=(
            f"Бюджет {payload.period_type.value} {payload.period_key} "
            f"({payload.currency.value}): {payload.limit_amount}"
        ),
        user=admin,
        changes={
            "old": {"limit_amount": old},
            "new": {"limit_amount": str(payload.limit_amount)},
        },
    )
    db.commit()
    db.refresh(budget)
    return _compute(db, budget, local_today(settings.tz))


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    _csrf: None = Depends(verify_csrf),
) -> Response:
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Бюджет не найден")
    audit.record(
        db,
        action="budget.deleted",
        entity_type="budget",
        entity_id=budget.id,
        description=f"Удалён бюджет {budget.period_type.value} {budget.period_key} ({budget.currency.value})",
        user=admin,
    )
    db.delete(budget)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
