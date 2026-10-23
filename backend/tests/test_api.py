"""API integration tests: auth, roles, business rules, budgets, audit, receipts."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, Budget, PaymentOccurrence, RecurringPayment, Role, User


# ---------------------------------------------------------------- authentication


def test_health_is_public(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    # must not leak configuration
    assert "password" not in resp.text.lower()
    assert "secret" not in resp.text.lower()


def test_me_requires_authentication(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rejects_bad_credentials(client, admin_user):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_and_me_and_logout(admin_api, client):
    resp = admin_api.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["role"] == "admin"
    # password hash must never be returned
    assert "password" not in resp.text

    assert admin_api.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_invalidates_session_server_side(admin_api, client, db):
    from app.models import UserSession

    admin_api.post("/api/v1/auth/logout")
    sessions = list(db.scalars(select(UserSession)))
    assert sessions and all(s.revoked_at is not None for s in sessions)


def test_csrf_required_for_mutations(admin_api):
    """An authenticated request without the CSRF header must be rejected."""
    resp = admin_api.client.post(
        "/api/v1/recurring-payments",
        json={
            "title": "No CSRF",
            "amount": "10.00",
            "currency": "RUB",
            "first_due_date": date.today().isoformat(),
        },
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]


def test_rate_limit_blocks_bruteforce(client, admin_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    from app.services.rate_limit import LoginRateLimiter
    import app.api.routers.auth as auth_module

    auth_module.login_limiter = LoginRateLimiter(3, 300)
    codes = [
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"}).status_code
        for _ in range(5)
    ]
    assert 429 in codes


# ------------------------------------------------------------------ authorization


def test_regular_user_cannot_create_payment(user_api):
    resp = user_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "Sneaky",
            "amount": "10.00",
            "currency": "RUB",
            "first_due_date": date.today().isoformat(),
        },
    )
    assert resp.status_code == 403


def test_regular_user_cannot_update_or_delete_payment(user_api, admin_api, sample_payment_spec):
    created = admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec).json()
    assert user_api.patch(f"/api/v1/recurring-payments/{created['id']}", json={"title": "hack"}).status_code == 403
    assert user_api.delete(f"/api/v1/recurring-payments/{created['id']}").status_code == 403


def test_regular_user_cannot_manage_users(user_api):
    assert user_api.get("/api/v1/users").status_code == 403
    assert user_api.post(
        "/api/v1/users", json={"username": "x", "password": "Password123"}
    ).status_code == 403


def test_regular_user_cannot_read_audit(user_api):
    assert user_api.get("/api/v1/audit").status_code == 403


def test_regular_user_cannot_edit_budget(user_api):
    resp = user_api.put(
        "/api/v1/budgets",
        json={"period_type": "month", "period_key": "2026-10", "currency": "RUB", "limit_amount": "1.00"},
    )
    assert resp.status_code == 403


def test_regular_user_can_view_shared_payments(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    resp = user_api.get("/api/v1/payment-occurrences")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ------------------------------------------------------------ payment lifecycle


def test_create_payment_returns_201_and_period(admin_api, sample_payment_spec):
    resp = admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Test VPS"
    assert body["occurrences_count"] >= 1
    assert body["is_active"] is True


def test_invalid_payload_is_rejected(admin_api):
    bad_amount = admin_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "Bad",
            "amount": "-100.00",
            "currency": "RUB",
            "first_due_date": date.today().isoformat(),
        },
    )
    assert bad_amount.status_code == 422

    bad_currency = admin_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "Bad",
            "amount": "10.00",
            "currency": "GBP",
            "first_due_date": date.today().isoformat(),
        },
    )
    assert bad_currency.status_code == 422

    empty_title = admin_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "   ",
            "amount": "10.00",
            "currency": "RUB",
            "first_due_date": date.today().isoformat(),
        },
    )
    assert empty_title.status_code == 422


def test_shared_status_visible_to_second_user(user_api, admin_api, sample_payment_spec, app, db):
    """A status change made by one user is visible to another user."""
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    occurrences = user_api.get("/api/v1/payment-occurrences").json()["items"]
    target = occurrences[0]

    mark = user_api.patch(f"/api/v1/payment-occurrences/{target['id']}", json={"is_paid": True})
    assert mark.status_code == 200
    assert mark.json()["is_paid"] is True

    # A brand-new, independent session must observe the same shared status.
    from tests.conftest import ApiSession

    other = ApiSession(app)
    try:
        other.login("user1", "UserPass123!")
        seen = other.get(f"/api/v1/payment-occurrences/{target['id']}").json()
        assert seen["is_paid"] is True
        assert seen["status"] == "paid_on_time"
    finally:
        other.close()


def test_correct_paid_date_recalculates_status(user_api, admin_api, sample_payment_spec, db):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    items = user_api.get("/api/v1/payment-occurrences").json()["items"]
    occ = items[0]
    due = date.fromisoformat(occ["due_date"])

    late = user_api.patch(
        f"/api/v1/payment-occurrences/{occ['id']}", json={"paid_at": (due + timedelta(days=2)).isoformat()}
    )
    assert late.json()["status"] == "paid_late"

    on_time = user_api.patch(
        f"/api/v1/payment-occurrences/{occ['id']}", json={"paid_at": (due - timedelta(days=1)).isoformat()}
    )
    body = on_time.json()
    assert body["status"] == "paid_on_time"
    # the deadline itself must not move
    assert body["due_date"] == occ["due_date"]


def test_unmark_restores_overdue_state(user_api, admin_api, db):
    today = date.today()
    due = today - timedelta(days=10)
    admin_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "Overdue rent",
            "amount": "5000.00",
            "currency": "RUB",
            "first_due_date": due.isoformat(),
            "anchor_day": due.day,
        },
    )
    items = user_api.get("/api/v1/payment-occurrences").json()["items"]
    target = next(i for i in items if i["due_date"] == due.isoformat())
    assert target["status"] == "overdue"

    user_api.patch(f"/api/v1/payment-occurrences/{target['id']}", json={"is_paid": True})
    after_pay = user_api.get(f"/api/v1/payment-occurrences/{target['id']}").json()
    assert after_pay["status"] == "paid_late"

    user_api.patch(f"/api/v1/payment-occurrences/{target['id']}", json={"is_paid": False})
    after_unmark = user_api.get(f"/api/v1/payment-occurrences/{target['id']}").json()
    assert after_unmark["status"] == "overdue"
    assert after_unmark["paid_at"] is None


def test_completion_keeps_history_and_stops_generation(admin_api, user_api, sample_payment_spec, db):
    created = admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec).json()
    pid = created["id"]
    before = admin_api.get(f"/api/v1/recurring-payments/{pid}/history").json()

    resp = admin_api.delete(f"/api/v1/recurring-payments/{pid}")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    after = admin_api.get(f"/api/v1/recurring-payments/{pid}/history").json()
    assert len(after) == len(before)
    assert len(after) > 0

    # Worker must not generate more periods for a completed payment.
    from app.services.generation import ensure_periods

    payment = db.get(RecurringPayment, pid)
    assert ensure_periods(db, payment) == 0
    db.commit()
    still = admin_api.get(f"/api/v1/recurring-payments/{pid}/history").json()
    assert len(still) == len(before)


def test_filters_and_pagination(admin_api, user_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    resp = user_api.get("/api/v1/payment-occurrences", params={"limit": 1, "offset": 0})
    body = resp.json()
    assert len(body["items"]) <= 1
    assert body["total"] >= 1

    filtered = user_api.get("/api/v1/payment-occurrences", params={"currency": "USD"})
    assert all(i["currency"] == "USD" for i in filtered.json()["items"])

    searched = user_api.get("/api/v1/payment-occurrences", params={"search": "Test VPS"})
    assert searched.json()["total"] >= 1

    none = user_api.get("/api/v1/payment-occurrences", params={"search": "zzz-no-match"})
    assert none.json()["total"] == 0


def test_missing_occurrence_returns_404(user_api):
    assert user_api.get("/api/v1/payment-occurrences/999999").status_code == 404


# ------------------------------------------------------------------ currencies


def test_currencies_are_not_summed_together(admin_api, user_api):
    today = date.today()
    for currency, amount in (("RUB", "1000.00"), ("USD", "100.00"), ("EUR", "50.00")):
        admin_api.post(
            "/api/v1/recurring-payments",
            json={
                "title": f"Payment {currency}",
                "amount": amount,
                "currency": currency,
                "first_due_date": (today + timedelta(days=5)).isoformat(),
                "anchor_day": (today + timedelta(days=5)).day,
                # yearly so exactly one period falls inside the 12-month horizon
                "recurrence": "yearly",
            },
        )
    summary = user_api.get("/api/v1/payments/summary").json()
    currencies = {t["currency"]: t for t in summary["by_currency"]}
    assert set(currencies) == {"RUB", "USD", "EUR"}
    assert Decimal(currencies["RUB"]["upcoming"]) == Decimal("1000.00")
    assert Decimal(currencies["USD"]["upcoming"]) == Decimal("100.00")
    assert Decimal(currencies["EUR"]["upcoming"]) == Decimal("50.00")


def test_dashboard_reports_integration_state(user_api):
    body = user_api.get("/api/v1/dashboard").json()
    assert "integrations" in body
    assert body["integrations"]["telegram_configured"] in (True, False)
    assert "totals" in body
    assert body["timezone"] == "Europe/Moscow"


# ----------------------------------------------------------------- users/admin


def test_admin_manages_users(admin_api, db):
    created = admin_api.post(
        "/api/v1/users",
        json={"username": "newuser", "password": "Password123", "role": "user"},
    )
    assert created.status_code == 201
    uid = created.json()["id"]

    promoted = admin_api.patch(f"/api/v1/users/{uid}", json={"role": "admin"})
    assert promoted.json()["role"] == "admin"

    deactivated = admin_api.delete(f"/api/v1/users/{uid}")
    assert deactivated.json()["is_active"] is False


def test_bootstrap_admin_is_protected(admin_api, db):
    admin = db.scalar(select(User).where(User.username == "admin"))
    admin.is_bootstrap = True
    db.commit()

    assert admin_api.delete(f"/api/v1/users/{admin.id}").status_code == 403
    assert admin_api.patch(f"/api/v1/users/{admin.id}", json={"role": "user"}).status_code == 403
    assert admin_api.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}).status_code == 403


def test_duplicate_username_rejected(admin_api):
    payload = {"username": "dup", "password": "Password123"}
    assert admin_api.post("/api/v1/users", json=payload).status_code == 201
    assert admin_api.post("/api/v1/users", json=payload).status_code == 409


def test_weak_password_rejected(admin_api):
    resp = admin_api.post("/api/v1/users", json={"username": "weak", "password": "123"})
    assert resp.status_code == 422


# --------------------------------------------------------------------- budgets


def test_budget_crud_and_calculation(admin_api, user_api):
    today = date.today()
    key = today.strftime("%Y-%m")
    admin_api.post(
        "/api/v1/recurring-payments",
        json={
            "title": "Budgeted",
            "amount": "3000.00",
            "currency": "RUB",
            "first_due_date": today.isoformat(),
            "anchor_day": today.day,
        },
    )
    created = admin_api.put(
        "/api/v1/budgets",
        json={"period_type": "month", "period_key": key, "currency": "RUB", "limit_amount": "10000.00"},
    )
    assert created.status_code == 200
    body = created.json()
    assert Decimal(body["planned_amount"]) >= Decimal("3000.00")
    assert body["usage_percent"] >= 0
    assert body["over_limit"] is False

    listed = user_api.get("/api/v1/budgets", params={"period_type": "month", "period_key": key}).json()
    assert any(b["currency"] == "RUB" for b in listed)

    over = admin_api.put(
        "/api/v1/budgets",
        json={"period_type": "month", "period_key": key, "currency": "RUB", "limit_amount": "1.00"},
    )
    assert over.json()["over_limit"] is True


def test_budget_currencies_are_separate(admin_api):
    today = date.today()
    key = today.strftime("%Y-%m")
    admin_api.put(
        "/api/v1/budgets",
        json={"period_type": "month", "period_key": key, "currency": "USD", "limit_amount": "500.00"},
    )
    budgets = admin_api.get("/api/v1/budgets").json()
    usd = [b for b in budgets if b["currency"] == "USD"]
    assert usd and Decimal(usd[0]["limit_amount"]) == Decimal("500.00")


# ----------------------------------------------------------------------- audit


def test_audit_records_real_actions(admin_api, user_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    items = user_api.get("/api/v1/payment-occurrences").json()["items"]
    user_api.patch(f"/api/v1/payment-occurrences/{items[0]['id']}", json={"is_paid": True})

    audit = admin_api.get("/api/v1/audit", params={"limit": 100}).json()
    actions = {item["action"] for item in audit["items"]}
    assert "auth.login" in actions
    assert "recurring_payment.created" in actions
    assert "payment_occurrence.updated" in actions

    # No secrets in audit payloads
    assert "password" not in admin_api.get("/api/v1/audit").text.lower()


# ------------------------------------------------------------------ attachments


def test_attachment_upload_and_download_requires_auth(admin_api, user_api, client, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    occ = admin_api.get("/api/v1/payment-occurrences").json()["items"][0]

    upload = user_api.post(
        f"/api/v1/attachments/occurrence/{occ['id']}",
        files={"file": ("receipt.pdf", b"%PDF-1.4 fake receipt", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["original_name"] == "receipt.pdf"

    assert user_api.get(f"/api/v1/attachments/{attachment['id']}/download").status_code == 200
    # unauthenticated access is denied
    client.cookies.clear()
    assert client.get(f"/api/v1/attachments/{attachment['id']}/download").status_code == 401


def test_attachment_rejects_bad_type(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    occ = admin_api.get("/api/v1/payment-occurrences").json()["items"][0]
    resp = user_api.post(
        f"/api/v1/attachments/occurrence/{occ['id']}",
        files={"file": ("evil.sh", b"#!/bin/sh\nrm -rf /", "application/x-sh")},
    )
    assert resp.status_code == 415


def test_attachment_rejects_oversize(user_api, admin_api, sample_payment_spec, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    occ = admin_api.get("/api/v1/payment-occurrences").json()["items"][0]
    resp = user_api.post(
        f"/api/v1/attachments/occurrence/{occ['id']}",
        files={"file": ("big.pdf", b"x" * (1024 * 1024 + 10), "application/pdf")},
    )
    assert resp.status_code == 413


def test_receipt_link_update(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    occ = admin_api.get("/api/v1/payment-occurrences").json()["items"][0]
    resp = user_api.patch(
        f"/api/v1/payment-occurrences/{occ['id']}",
        json={"receipt_url": "https://receipts.example.com/abc"},
    )
    assert resp.json()["receipt_url"] == "https://receipts.example.com/abc"


# ------------------------------------------------------------------ openapi


def test_openapi_matches_routes(client):
    schema = client.get("/api/v1/openapi.json").json()
    paths = schema["paths"]
    required = [
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/recurring-payments",
        "/api/v1/recurring-payments/{payment_id}",
        "/api/v1/payment-occurrences",
        "/api/v1/payment-occurrences/{occurrence_id}",
        "/api/v1/payments/summary",
        "/api/v1/users",
        "/api/v1/users/{user_id}",
        "/api/v1/dashboard",
        "/api/v1/calendar",
        "/api/v1/budgets",
        "/api/v1/audit",
        "/api/v1/health",
    ]
    missing = [p for p in required if p not in paths]
    assert not missing, f"missing from OpenAPI: {missing}"


def test_swagger_ui_available(client):
    assert client.get("/api/v1/docs").status_code == 200


# ------------------------------------------------------------------ calendar


def test_calendar_returns_real_periods(user_api, admin_api, sample_payment_spec):
    created = admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec).json()
    # Use the month of the period that actually exists, not "today's month".
    history = admin_api.get(f"/api/v1/recurring-payments/{created['id']}/history").json()
    month = history[0]["due_date"][:7]
    resp = user_api.get("/api/v1/calendar", params={"month": month})
    assert resp.status_code == 200
    body = resp.json()
    assert body["month"] == month
    total_items = sum(len(d["items"]) for d in body["days"])
    assert total_items >= 1
    # Calendar entries must be real DB rows, identifiable by id.
    assert all(item["id"] for d in body["days"] for item in d["items"])


def test_calendar_rejects_bad_month(user_api):
    assert user_api.get("/api/v1/calendar", params={"month": "nope"}).status_code == 422


# ------------------------------------------------------------------ errors


def test_internal_errors_do_not_leak_details(user_api):
    # An invalid id type yields a clean validation error, not a traceback.
    resp = user_api.get("/api/v1/payment-occurrences/not-an-int")
    assert resp.status_code == 422
    assert "Traceback" not in resp.text
    assert "psycopg" not in resp.text


# ------------------------------------------------- occurrence list ordering


def test_occurrences_default_sort_is_ascending_by_due_date(user_api, admin_api, sample_payment_spec):
    """Urgent periods must come first: the overdue one must not be on the last page."""
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    items = user_api.get("/api/v1/payment-occurrences", params={"limit": 100}).json()["items"]
    assert len(items) > 1
    dates = [item["due_date"] for item in items]
    assert dates == sorted(dates), f"expected ascending order, got {dates[:5]}"


def test_occurrences_direction_desc_reverses_order(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    asc = user_api.get(
        "/api/v1/payment-occurrences", params={"direction": "asc", "limit": 100}
    ).json()["items"]
    desc = user_api.get(
        "/api/v1/payment-occurrences", params={"direction": "desc", "limit": 100}
    ).json()["items"]
    assert [i["due_date"] for i in desc] == list(reversed([i["due_date"] for i in asc]))


def test_occurrences_sort_by_amount(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    items = user_api.get(
        "/api/v1/payment-occurrences", params={"sort": "amount", "direction": "asc", "limit": 100}
    ).json()["items"]
    amounts = [float(i["amount"]) for i in items]
    assert amounts == sorted(amounts)


def test_occurrences_reject_unknown_sort_column(user_api):
    """A non-whitelisted column must be rejected, never passed to SQL."""
    resp = user_api.get(
        "/api/v1/payment-occurrences", params={"sort": "amount; DROP TABLE users"}
    )
    assert resp.status_code == 422
    assert user_api.get("/api/v1/payment-occurrences", params={"direction": "sideways"}).status_code == 422


def test_occurrences_filters_combine(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    body = user_api.get(
        "/api/v1/payment-occurrences",
        params={"currency": "RUB", "status": "pending", "limit": 100},
    ).json()
    assert all(i["currency"] == "RUB" for i in body["items"])
    assert all(i["status"] == "pending" for i in body["items"])


def test_occurrences_pagination_is_stable(user_api, admin_api, sample_payment_spec):
    admin_api.post("/api/v1/recurring-payments", json=sample_payment_spec)
    all_items = user_api.get("/api/v1/payment-occurrences", params={"limit": 500}).json()["items"]
    page1 = user_api.get("/api/v1/payment-occurrences", params={"limit": 3, "offset": 0}).json()["items"]
    page2 = user_api.get("/api/v1/payment-occurrences", params={"limit": 3, "offset": 3}).json()["items"]
    assert [i["id"] for i in page1 + page2] == [i["id"] for i in all_items[:6]]


# ------------------------------------------------------- configuration validation


def test_config_validation_rejects_short_secret_key():
    """A weak SECRET_KEY must be reported as a fatal configuration problem."""
    from app.config import Settings

    s = Settings(
        SECRET_KEY="short",
        ADMIN_PASSWORD="StrongPassword123!",
        _env_file=None,
    )
    problems = s.validate_runtime()
    assert any("SECRET_KEY" in p for p in problems)


def test_config_validation_rejects_missing_admin_password():
    from app.config import Settings

    s = Settings(
        SECRET_KEY="a-sufficiently-long-secret-value",
        ADMIN_PASSWORD="",
        _env_file=None,
    )
    problems = s.validate_runtime()
    assert any("ADMIN_PASSWORD" in p for p in problems)


def test_config_validation_accepts_valid_settings():
    from app.config import Settings

    s = Settings(
        SECRET_KEY="a-sufficiently-long-secret-value",
        ADMIN_PASSWORD="StrongPassword123!",
        _env_file=None,
    )
    assert s.validate_runtime() == []


def test_config_validation_problems_never_contain_values():
    """Error messages must name the variable without echoing its value."""
    from app.config import Settings

    secret = "leak-me-please-0123456789"
    s = Settings(SECRET_KEY=secret, ADMIN_PASSWORD="x", _env_file=None)
    for problem in s.validate_runtime():
        assert secret not in problem


def test_config_validation_production_requires_secure_cookie():
    from app.config import Settings

    s = Settings(
        APP_ENV="production",
        COOKIE_SECURE=False,
        SECRET_KEY="a-sufficiently-long-secret-value",
        ADMIN_PASSWORD="StrongPassword123!",
        _env_file=None,
    )
    problems = s.validate_runtime()
    assert any("COOKIE_SECURE" in p for p in problems)


def test_config_validation_production_rejects_placeholder_secret():
    from app.config import Settings

    s = Settings(
        APP_ENV="production",
        COOKIE_SECURE=True,
        SECRET_KEY="http://localhost-secret-key-value",
        ADMIN_PASSWORD="StrongPassword123!",
        _env_file=None,
    )
    problems = s.validate_runtime()
    assert any("placeholder" in p for p in problems)


def test_app_refuses_to_start_with_bad_config(monkeypatch):
    """create_app() must fail fast instead of serving with broken config."""
    import app.main as main_module
    from app.config import Settings

    bad = Settings(SECRET_KEY="short", ADMIN_PASSWORD="", _env_file=None)
    monkeypatch.setattr(main_module, "settings", bad)
    with pytest.raises(RuntimeError) as exc:
        main_module.create_app()
    assert "SECRET_KEY" in str(exc.value)
    assert "short" not in str(exc.value)  # never echo the value


def test_config_validation_production_rejects_placeholder_admin_password():
    from app.config import Settings

    s = Settings(
        APP_ENV="production",
        COOKIE_SECURE=True,
        SECRET_KEY="a-sufficiently-long-secret-value",
        ADMIN_PASSWORD="change-me-strong-password",
        _env_file=None,
    )
    problems = s.validate_runtime()
    assert any("ADMIN_PASSWORD" in p for p in problems)


def test_config_validation_development_allows_placeholder_password():
    """The demo default is fine for local development."""
    from app.config import Settings

    s = Settings(
        APP_ENV="development",
        SECRET_KEY="a-sufficiently-long-secret-value",
        ADMIN_PASSWORD="change-me-strong-password",
        _env_file=None,
    )
    assert s.validate_runtime() == []
