#!/usr/bin/env python3
"""Live end-to-end verification against a running Invoice Keeper stack.

Exercises the real HTTP API through the reverse proxy: role enforcement,
shared status, overdue arithmetic, paid-date correction, unmarking, period
independence, completion preserving history, budgets and audit.

Usage:  python scripts/verify_stack.py [base_url]
Exit code 0 means every check passed.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("VERIFY_BASE_URL", "http://localhost:8080")
API = f"{BASE}/api/v1"

# Defaults match the synthetic demo accounts; override on a real stand.
ADMIN = (os.getenv("VERIFY_ADMIN_USERNAME", "admin"), os.getenv("VERIFY_ADMIN_PASSWORD", "DemoAdmin123!"))
USER = (os.getenv("VERIFY_USER_USERNAME", "demo_user"), os.getenv("VERIFY_USER_PASSWORD", "DemoUser123!"))

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} - {detail}")
        print(f"  FAIL  {name} - {detail}")


class Session:
    """Independent cookie jar + CSRF token, mirroring a real browser."""

    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE, timeout=20.0)
        self.csrf = ""

    def login(self, username: str, password: str) -> bool:
        resp = self.client.post(
            f"{API}/auth/login", json={"username": username, "password": password}
        )
        if resp.status_code != 200:
            return False
        self.csrf = resp.json()["csrf_token"]
        return True

    def _headers(self, method: str) -> dict:
        if method.upper() in ("GET", "HEAD"):
            return {}
        return {"X-CSRF-Token": self.csrf}

    def request(self, method: str, path: str, **kwargs):
        return self.client.request(method, f"{API}{path}", headers=self._headers(method), **kwargs)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def close(self) -> None:
        self.client.close()


def main() -> int:
    print(f"== Invoice Keeper stack verification against {BASE} ==\n")

    print("[1] Health and public docs")
    anon = httpx.Client(base_url=BASE, timeout=20.0)
    health = anon.get(f"{API}/health")
    check("health returns ok", health.status_code == 200 and health.json()["status"] == "ok")
    check("health reports database ok", health.json().get("database") == "ok")
    check("swagger UI is reachable", anon.get(f"{API}/docs").status_code == 200)
    openapi = anon.get(f"{API}/openapi.json")
    check("openapi json is valid", openapi.status_code == 200 and "paths" in openapi.json())

    print("\n[2] Unauthenticated access is rejected")
    check("me without session is 401", anon.get(f"{API}/auth/me").status_code == 401)
    check("payments without session is 401", anon.get(f"{API}/payment-occurrences").status_code == 401)
    check("audit without session is 401", anon.get(f"{API}/audit").status_code == 401)
    check(
        "create payment without session is 401",
        anon.post(f"{API}/recurring-payments", json={"title": "x"}).status_code == 401,
    )

    admin = Session()
    user = Session()
    check("admin login succeeds", admin.login(*ADMIN))
    check("regular user login succeeds", user.login(*USER))

    print("\n[3] Role enforcement on the server")
    forbidden_create = user.post(
        "/recurring-payments",
        json={
            "title": "Forbidden",
            "amount": "10.00",
            "currency": "RUB",
            "first_due_date": date.today().isoformat(),
        },
    )
    check("user cannot create a payment (403)", forbidden_create.status_code == 403,
          f"got {forbidden_create.status_code}")
    check("user cannot list users (403)", user.get("/users").status_code == 403)
    check("user cannot read audit log (403)", user.get("/audit").status_code == 403)
    check(
        "user cannot edit budgets (403)",
        user.put(
            "/budgets",
            json={"period_type": "month", "period_key": "2026-10", "currency": "RUB", "limit_amount": "1.00"},
        ).status_code == 403,
    )

    print("\n[4] Admin creates a recurring payment")
    today = date.today()
    due = today - timedelta(days=7)
    created = admin.post(
        "/recurring-payments",
        json={
            "title": "Verify Stack Payment",
            "description": "created by verify_stack.py",
            "amount": "2500.00",
            "currency": "RUB",
            "first_due_date": due.isoformat(),
            "recurrence": "monthly",
            "anchor_day": due.day,
        },
    )
    check("payment created (201)", created.status_code == 201, created.text[:200])
    if created.status_code != 201:
        return report()
    payment_id = created.json()["id"]
    check("periods were generated", created.json()["occurrences_count"] >= 1)

    history = admin.get(f"/recurring-payments/{payment_id}/history").json()
    overdue_occ = next((o for o in history if o["due_date"] == due.isoformat()), None)
    check("overdue period exists", overdue_occ is not None)
    check("overdue status is computed", bool(overdue_occ) and overdue_occ["status"] == "overdue",
          overdue_occ and overdue_occ["status"])
    check("overdue flag is set", bool(overdue_occ) and overdue_occ["is_overdue"] is True)

    future_periods = [o for o in history if o["due_date"] > today.isoformat()]
    check("future periods exist despite the overdue one", len(future_periods) >= 1)

    print("\n[5] Payment status is shared between users")
    seen_by_user = user.get(f"/payment-occurrences/{overdue_occ['id']}")
    check("user sees the same period", seen_by_user.status_code == 200)
    check("user sees it as overdue", seen_by_user.json()["status"] == "overdue")

    mark = user.patch(f"/payment-occurrences/{overdue_occ['id']}", json={"is_paid": True})
    check("user can mark as paid", mark.status_code == 200, mark.text[:200])
    check("status becomes paid_late", mark.json()["status"] == "paid_late", mark.json().get("status"))
    check("paid_at is today", mark.json()["paid_at"] == today.isoformat(), str(mark.json().get("paid_at")))

    other = Session()
    other.login(*ADMIN)
    fresh_view = other.get(f"/payment-occurrences/{overdue_occ['id']}").json()
    check("second session sees paid status", fresh_view["is_paid"] is True)
    check("second session sees same status value", fresh_view["status"] == "paid_late")
    other.close()

    print("\n[6] Correcting the actual payment date recalculates lateness")
    corrected = user.patch(
        f"/payment-occurrences/{overdue_occ['id']}",
        json={"paid_at": (due - timedelta(days=1)).isoformat()},
    )
    check("status becomes paid_on_time", corrected.json()["status"] == "paid_on_time",
          corrected.json().get("status"))
    check("due_date did not move", corrected.json()["due_date"] == due.isoformat(),
          corrected.json().get("due_date"))

    print("\n[7] Removing the paid mark restores overdue")
    unmarked = user.patch(f"/payment-occurrences/{overdue_occ['id']}", json={"is_paid": False})
    check("unmark succeeds", unmarked.status_code == 200)
    check("status returns to overdue", unmarked.json()["status"] == "overdue",
          unmarked.json().get("status"))
    check("paid_at is cleared", unmarked.json()["paid_at"] is None)
    check("period row still exists", admin.get(f"/payment-occurrences/{overdue_occ['id']}").status_code == 200)

    print("\n[8] Periods are independent")
    user.patch(f"/payment-occurrences/{overdue_occ['id']}", json={"is_paid": True})
    history = admin.get(f"/recurring-payments/{payment_id}/history").json()
    first = next(o for o in history if o["due_date"] == due.isoformat())
    later = [o for o in history if o["due_date"] > due.isoformat()]
    check("first period is paid", first["is_paid"] is True)
    check("later periods remain unpaid", all(o["is_paid"] is False for o in later),
          str([o["is_paid"] for o in later]))
    check("later periods exist and are independent", len(later) >= 1)

    print("\n[9] Server-side validation")
    check(
        "negative amount rejected",
        admin.post(
            "/recurring-payments",
            json={"title": "Bad", "amount": "-1.00", "currency": "RUB", "first_due_date": today.isoformat()},
        ).status_code == 422,
    )
    check(
        "unsupported currency rejected",
        admin.post(
            "/recurring-payments",
            json={"title": "Bad", "amount": "1.00", "currency": "GBP", "first_due_date": today.isoformat()},
        ).status_code == 422,
    )
    check(
        "invalid anchor day rejected",
        admin.post(
            "/recurring-payments",
            json={
                "title": "Bad",
                "amount": "1.00",
                "currency": "RUB",
                "first_due_date": today.isoformat(),
                "anchor_day": 45,
            },
        ).status_code == 422,
    )

    print("\n[10] Budgets are per-currency")
    month_key = today.strftime("%Y-%m")
    budget = admin.put(
        "/budgets",
        json={"period_type": "month", "period_key": month_key, "currency": "RUB", "limit_amount": "1.00"},
    )
    check("budget saved", budget.status_code == 200, budget.text[:200])
    if budget.status_code == 200:
        check("budget reports over-limit correctly", budget.json()["over_limit"] is True, str(budget.json()))
        check("budget has its own currency", budget.json()["currency"] == "RUB")
    listed = admin.get("/budgets", params={"period_type": "month", "period_key": month_key}).json()
    check("budget list is filterable", any(b["currency"] == "RUB" for b in listed))

    print("\n[11] Audit log records real actions")
    audit = admin.get("/audit", params={"limit": 200}).json()
    actions = {item["action"] for item in audit["items"]}
    check("login is audited", "auth.login" in actions, str(sorted(actions))[:300])
    check("payment creation is audited", "recurring_payment.created" in actions)
    check("payment status change is audited", "payment_occurrence.updated" in actions)
    check("audit contains no password material", "password" not in str(audit).lower())

    print("\n[12] Completing a payment preserves history")
    before = admin.get(f"/recurring-payments/{payment_id}/history").json()
    deactivated = admin.delete(f"/recurring-payments/{payment_id}")
    check("completion succeeds", deactivated.status_code == 200, deactivated.text[:200])
    check("payment is inactive", deactivated.json()["is_active"] is False)
    after = admin.get(f"/recurring-payments/{payment_id}/history").json()
    check("history length unchanged", len(after) == len(before), f"{len(before)} -> {len(after)}")
    check("paid period retained", any(o["is_paid"] for o in after))

    print("\n[13] Currencies are never merged")
    summary = user.get("/payments/summary").json()
    codes = {t["currency"] for t in summary["by_currency"]}
    check("summary lists each currency separately", codes == {"RUB", "USD", "EUR"}, str(codes))
    check("each currency has its own numbers", all(Decimal(t["upcoming"]) >= 0 for t in summary["by_currency"]))

    print("\n[14] Calendar reflects real rows")
    cal_month = due.strftime("%Y-%m")
    calendar = user.get("/calendar", params={"month": cal_month})
    check("calendar returns 200", calendar.status_code == 200)
    if calendar.status_code == 200:
        items = [i for d in calendar.json()["days"] for i in d["items"]]
        check("calendar has real entries", len(items) >= 1, str(len(items)))
        check("calendar entries carry ids", all(i.get("id") for i in items))

    print("\n[15] Logout invalidates the session server-side")
    admin.post("/auth/logout")
    check("session invalid after logout", admin.get("/auth/me").status_code == 401)

    admin.close()
    user.close()
    anon.close()
    return report()


def report() -> int:
    print(f"\n{'=' * 60}")
    print(f"PASSED: {len(PASSED)}   FAILED: {len(FAILED)}")
    if FAILED:
        print("\nFailures:")
        for item in FAILED:
            print(f"  - {item}")
        return 1
    print("All stack checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
