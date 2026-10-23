"""Safe, idempotent bootstrap: schema creation + admin account from env."""
from __future__ import annotations

import logging
import sys
import time

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import Role, User
from app.services.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(levelname)s [bootstrap] %(message)s")
log = logging.getLogger("bootstrap")


def wait_for_db(attempts: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            log.info("database not ready (%s/%s)", attempt, attempts)
            time.sleep(delay)
    raise SystemExit("Database is unavailable after retries")


def bootstrap_admin() -> None:
    """Create the admin once. An existing admin is never overwritten."""
    if not settings.ADMIN_PASSWORD:
        raise SystemExit("ADMIN_PASSWORD is required to bootstrap the admin account")

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == settings.ADMIN_USERNAME))
        if existing is not None:
            if not existing.is_bootstrap:
                existing.is_bootstrap = True
                db.commit()
            log.info("admin '%s' already exists — password left untouched", existing.username)
            return

        admin = User(
            username=settings.ADMIN_USERNAME,
            email=settings.ADMIN_EMAIL,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role=Role.admin,
            is_active=True,
            is_bootstrap=True,
        )
        db.add(admin)
        db.commit()
        log.info("bootstrap admin '%s' created", admin.username)


def main() -> None:
    problems = settings.validate_runtime()
    if problems:
        for problem in problems:
            log.error("configuration problem: %s", problem)
        sys.exit(1)

    wait_for_db()
    # Migrations are the source of truth; create_all is a safety net for a fresh
    # database so the app can start even before `alembic upgrade head` runs.
    Base.metadata.create_all(bind=engine)
    bootstrap_admin()
    log.info("bootstrap complete")


if __name__ == "__main__":
    main()
