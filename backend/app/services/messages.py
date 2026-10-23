"""Notification message templates (shared by Telegram and email)."""
from __future__ import annotations

from datetime import date

from app.models import NotificationKind, PaymentOccurrence, RecurringPayment
from app.services.dates import days_until

_CURRENCY_SYMBOL = {"RUB": "RUB", "USD": "USD", "EUR": "EUR"}

_MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def format_amount(amount, currency: str) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".00", "") + f" {_CURRENCY_SYMBOL.get(currency, currency)}"


def format_date_ru(value: date) -> str:
    return f"{value.day} {_MONTHS_RU[value.month]}"


def days_phrase(due_date: date, today: date) -> str:
    delta = days_until(due_date, today)
    if delta > 1:
        return f"Осталось {delta} дн."
    if delta == 1:
        return "Остался 1 день."
    if delta == 0:
        return "Срок сегодня."
    if delta == -1:
        return "Просрочка 1 день."
    return f"Просрочка {-delta} дн."


def build_message(
    occurrence: PaymentOccurrence,
    payment: RecurringPayment,
    *,
    kind: NotificationKind,
    today: date,
) -> tuple[str, str]:
    """Return (telegram_html_text, plain_text)."""
    amount = format_amount(occurrence.amount, occurrence.currency.value)
    due = format_date_ru(occurrence.due_date)
    phrase = days_phrase(occurrence.due_date, today)

    if kind == NotificationKind.overdue:
        header = "Платёж просрочен"
        status_line = "Статус: просрочено и не оплачено"
    else:
        header = "Скоро срок оплаты"
        status_line = "Статус: ожидает оплаты"

    html = (
        f"<b>{header}: {payment.title}</b>\n"
        f"Сумма: {amount}\n"
        f"Срок: {due}\n"
        f"{phrase}\n"
        f"{status_line}\n\n"
        f"Нажмите «Оплачено», чтобы отметить платёж."
    )
    plain = (
        f"{header}: {payment.title}\n"
        f"Сумма: {amount}\n"
        f"Срок: {due}\n"
        f"{phrase}\n"
        f"{status_line}"
    )
    return html, plain
