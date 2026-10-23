"""Invoice Keeper — FastAPI application factory."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings
from app.services import payments as payments_service

DESCRIPTION = """
**Invoice Keeper** — учёт регулярных платежей: сроки, фактическая оплата,
просрочки, общая история для всех пользователей, Telegram-уведомления,
бюджеты и журнал аудита.
"""


def create_app() -> FastAPI:
    # Fail fast with a readable message instead of serving with broken config.
    # Problems are reported by name only — never with their values.
    problems = settings.validate_runtime()
    if problems:
        raise RuntimeError(
            "Invalid configuration: " + "; ".join(problems)
        )

    app = FastAPI(
        title=settings.APP_NAME,
        description=DESCRIPTION,
        version="1.0.0",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(payments_service.DomainError)
    async def domain_error_handler(_request: Request, exc: payments_service.DomainError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        # Never leak tracebacks, SQL text or configuration to the client.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Внутренняя ошибка сервера",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
