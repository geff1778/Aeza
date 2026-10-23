"""Security helpers: password hashing, session tokens, CSRF."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

# Hashing a session token before storage means a DB leak does not hand over
# live sessions. Tokens are high-entropy so a fast hash is sufficient here.
_TOKEN_HASH_PEPPER = "invoice-keeper-session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256((_TOKEN_HASH_PEPPER + token).encode()).hexdigest()


def session_expiry(hours: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
