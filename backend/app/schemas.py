"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import BudgetPeriod, Currency, NotificationChannel, Recurrence, Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    role: Role
    is_active: bool
    is_bootstrap: bool
    created_at: datetime


class MeOut(UserOut):
    csrf_token: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    email: EmailStr | None = None
    role: Role = Role.user


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=256)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None


class RecurringPaymentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency
    first_due_date: date
    recurrence: Recurrence = Recurrence.monthly
    anchor_day: int | None = Field(default=None, ge=1, le=31)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название не может быть пустым")
        return v


class RecurringPaymentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: Currency | None = None
    first_due_date: date | None = None
    recurrence: Recurrence | None = None
    anchor_day: int | None = Field(default=None, ge=1, le=31)
    is_active: bool | None = None


class RecurringPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    amount: Decimal
    currency: Currency
    recurrence: Recurrence
    anchor_day: int
    first_due_date: date
    is_active: bool
    created_at: datetime
    updated_at: datetime
    occurrences_count: int = 0
    unpaid_count: int = 0
    overdue_count: int = 0


class OccurrenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recurring_payment_id: int
    due_date: date
    amount: Decimal
    currency: Currency
    is_paid: bool
    paid_at: date | None
    receipt_url: str | None
    created_at: datetime
    updated_at: datetime
    status: str
    status_label: str
    days_until_due: int
    is_overdue: bool
    payment_title: str = ""
    recurrence: Recurrence = Recurrence.monthly
    attachment_count: int = 0


class OccurrenceListOut(BaseModel):
    items: list[OccurrenceOut]
    total: int


class OccurrenceUpdate(BaseModel):
    is_paid: bool | None = None
    paid_at: date | None = None
    receipt_url: str | None = Field(default=None, max_length=1000)


class BudgetUpsert(BaseModel):
    period_type: BudgetPeriod
    period_key: str = Field(min_length=4, max_length=10)
    currency: Currency
    limit_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class BudgetOut(BaseModel):
    id: int
    period_type: BudgetPeriod
    period_key: str
    currency: Currency
    limit_amount: Decimal
    planned_amount: Decimal
    actual_amount: Decimal
    remaining: Decimal
    usage_percent: float
    over_limit: bool


class CurrencyTotals(BaseModel):
    currency: Currency
    upcoming: Decimal
    overdue: Decimal
    paid: Decimal


class DashboardOut(BaseModel):
    today: date
    timezone: str
    totals: list[CurrencyTotals]
    due_soon_count: int
    overdue_count: int
    paid_count: int
    upcoming: list[OccurrenceOut]
    recent_activity: list["AuditOut"]
    integrations: dict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_label: str
    action: str
    entity_type: str
    entity_id: str | None
    description: str
    changes: dict | None
    created_at: datetime


class AuditListOut(BaseModel):
    items: list[AuditOut]
    total: int


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurrence_id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class CalendarDay(BaseModel):
    date: date
    items: list[OccurrenceOut]


class CalendarOut(BaseModel):
    month: str
    days: list[CalendarDay]


class SummaryOut(BaseModel):
    today: date
    timezone: str
    by_currency: list[CurrencyTotals]
    by_month: list[dict]
    status_counts: dict
    overdue_count: int


class NotificationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurrence_id: int
    channel: NotificationChannel
    kind: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class IntegrationStatus(BaseModel):
    telegram_configured: bool
    telegram_hint: str | None = None
    smtp_configured: bool
    smtp_hint: str | None = None


class HealthOut(BaseModel):
    status: str
    database: str
    timezone: str
    version: str


DashboardOut.model_rebuild()
