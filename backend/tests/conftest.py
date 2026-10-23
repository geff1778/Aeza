"""Shared pytest fixtures.

The test database is separate from the development one and is dropped/recreated
per session, so tests never touch user data.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

# Must be set before importing the application so the engine points at the
# throwaway test database.
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "invoice_test")
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql+psycopg://invoice:invoice@localhost:55432/{TEST_DB_NAME}",
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789")
os.environ.setdefault("ADMIN_PASSWORD", "TestAdmin123!")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("APP_TIMEZONE", "Europe/Moscow")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")
os.environ.setdefault("UPLOAD_DIR", "/tmp/invoice_test_uploads")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.models import Currency, Recurrence, Role, User  # noqa: E402
from app.services.security import hash_password  # noqa: E402

engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The login limiter is process-global; reset it so tests stay independent."""
    import app.api.routers.auth as auth_module
    from app.services.rate_limit import LoginRateLimiter

    original = auth_module.login_limiter
    auth_module.login_limiter = LoginRateLimiter(
        settings.LOGIN_RATE_LIMIT_ATTEMPTS, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    )
    yield
    auth_module.login_limiter = original


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate everything between tests for isolation."""
    tables = ", ".join(
        f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app():
    from app.main import create_app

    application = create_app()

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def make_user(db, username: str, password: str, role: Role = Role.user) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db) -> User:
    return make_user(db, "admin", "AdminPass123!", Role.admin)


@pytest.fixture
def regular_user(db) -> User:
    return make_user(db, "user1", "UserPass123!", Role.user)


class ApiSession:
    """An independent browser session: its own cookie jar and CSRF token.

    Each instance gets a separate ``TestClient`` so logging in as one user does
    not overwrite another user's session — which is exactly the situation the
    shared-status requirement is about.
    """

    def __init__(self, app) -> None:
        self._ctx = TestClient(app)
        self.client = self._ctx.__enter__()
        self.csrf = ""

    def close(self) -> None:
        self._ctx.__exit__(None, None, None)

    def login(self, username: str, password: str) -> "ApiSession":
        resp = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert resp.status_code == 200, resp.text
        self.csrf = resp.json()["csrf_token"]
        return self

    def request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            headers["X-CSRF-Token"] = self.csrf
        return self.client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture
def admin_api(app, admin_user) -> ApiSession:
    session = ApiSession(app).login("admin", "AdminPass123!")
    yield session
    session.close()


@pytest.fixture
def user_api(app, regular_user) -> ApiSession:
    session = ApiSession(app).login("user1", "UserPass123!")
    yield session
    session.close()


@pytest.fixture
def sample_payment_spec():
    today = date.today()
    return {
        "title": "Test VPS",
        "amount": "1500.00",
        "currency": Currency.RUB.value,
        "first_due_date": (today + timedelta(days=10)).isoformat(),
        "recurrence": Recurrence.monthly.value,
        "anchor_day": (today + timedelta(days=10)).day,
        "description": "test payment",
    }
