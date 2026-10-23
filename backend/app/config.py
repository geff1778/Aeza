"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"
    APP_TIMEZONE: str = "Europe/Moscow"
    APP_NAME: str = "Invoice Keeper"
    APP_PUBLIC_URL: str = "http://localhost:8080"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://invoice:invoice@localhost:5432/invoice"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""
    ADMIN_EMAIL: str | None = None

    SECRET_KEY: str = ""
    SESSION_COOKIE_NAME: str = "invoice_session"
    SESSION_TTL_HOURS: int = 72
    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:8080,http://localhost:5173"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    TELEGRAM_API_BASE: str = "https://api.telegram.org"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TO: str = ""
    SMTP_USE_TLS: bool = True

    UPLOAD_DIR: str = "/data/uploads"
    MAX_UPLOAD_MB: int = 10

    GENERATION_HORIZON_MONTHS: int = 12
    REMINDER_DAYS_BEFORE: int = 3
    WORKER_INTERVAL_SECONDS: int = 300
    WORKER_MAX_ATTEMPTS: int = 5

    LOGIN_RATE_LIMIT_ATTEMPTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    SEED_DEMO_DATA: bool = False

    @field_validator("APP_TIMEZONE")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.APP_TIMEZONE)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def telegram_allowed_user_ids(self) -> set[int]:
        result: set[int] = set()
        for chunk in self.TELEGRAM_ALLOWED_USER_IDS.split(","):
            chunk = chunk.strip()
            if chunk:
                result.add(int(chunk))
        return result

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM)

    def validate_runtime(self) -> list[str]:
        """Return a list of fatal configuration problems."""
        problems: list[str] = []
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 16:
            problems.append("SECRET_KEY must be set to a random string of >=16 chars")
        if not self.ADMIN_PASSWORD:
            problems.append("ADMIN_PASSWORD must be set to bootstrap the admin account")
        if self.APP_ENV == "production":
            if not self.COOKIE_SECURE:
                problems.append("COOKIE_SECURE must be true in production")
            if "localhost" in self.SECRET_KEY:
                problems.append("SECRET_KEY looks like a placeholder value")
            if self.ADMIN_PASSWORD.lower().startswith("change-me"):
                problems.append(
                    "ADMIN_PASSWORD is still the placeholder from .env.example; "
                    "set a real password in production"
                )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
