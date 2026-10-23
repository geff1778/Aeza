"""Simple in-process rate limiter for login attempts.

Deliberately not distributed: it only needs to blunt brute-force attempts from a
single client. A shared store can be added later without changing callers.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from app.config import settings


class LoginRateLimiter:
    def __init__(self, attempts: int, window_seconds: int) -> None:
        self.attempts = attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.attempts:
            return False
        bucket.append(now)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


login_limiter = LoginRateLimiter(
    settings.LOGIN_RATE_LIMIT_ATTEMPTS, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
)
