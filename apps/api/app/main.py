"""FastAPI application factory."""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.errors import RateLimited, envelope, install_error_handlers
from app.logging_setup import configure_logging, request_id_var
from app.routers import account, applications, auth, documents, insights, jobs, profile
from app.security.deps import CSRF_COOKIE, CSRF_HEADER
from app.security.ratelimit import enforce

log = logging.getLogger("jobpilot.http")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("WARNING" if settings.app_env == "test" else "INFO")
    app = FastAPI(
        title="JobPilot AI API",
        version="1.0.0",
        description="Compliance-first, human-in-the-loop job-search assistant. Every write endpoint requires the "
        "X-CSRF-Token header (double-submit cookie from GET /api/auth/csrf).",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid = rid[:64] if rid.replace("-", "").isalnum() else uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        started = time.monotonic()
        try:
            if request.url.path.startswith("/api/"):
                client = request.client.host if request.client else "unknown"
                try:
                    enforce("ip_global", client)
                except RateLimited as exc:
                    return envelope(request, 429, exc.code, exc.message, exc.details)
                if request.method in UNSAFE:
                    cookie = request.cookies.get(CSRF_COOKIE)
                    header = request.headers.get(CSRF_HEADER)
                    if not cookie or not header or not secrets.compare_digest(cookie, header):
                        return envelope(
                            request, 403, "csrf_failed", "Missing or invalid CSRF token. Reload the page and try again."
                        )
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log.info(
            "request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "If-Match", "X-Request-ID"],
        expose_headers=["ETag", "X-Request-ID", "Idempotent-Replayed"],
    )

    @app.get("/healthz", tags=["health"])
    @app.get("/api/healthz", tags=["health"], include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    @app.get("/api/readyz", tags=["health"], include_in_schema=False)
    async def readyz(response: Response) -> dict[str, str]:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            response.status_code = 503
            return {"status": "unavailable", "database": "error"}
        return {"status": "ready", "database": "ok", "ai_provider": settings.llm_provider}

    for r in (auth, profile, jobs, documents, applications, insights, account):
        app.include_router(r.router)
    return app


app = create_app()
