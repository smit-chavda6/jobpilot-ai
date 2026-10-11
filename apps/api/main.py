"""JobPilot AI FastAPI Main Application Entrypoint."""

import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.config import settings
from apps.api.logging_utils import setup_logging
from apps.api.routers.applications import router as applications_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.facts import router as facts_router
from apps.api.routers.jobs import router as jobs_router
from apps.api.routers.matching import router as matching_router
from apps.api.routers.profile import router as profile_router
from apps.api.routers.resumes import router as resumes_router

setup_logging(settings.LOG_LEVEL)

app = FastAPI(
    title="JobPilot AI API",
    description="Compliance-first, human-in-the-loop AI job search assistant.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    """Assigns unique correlation/request_id to every request and injects into response headers."""
    req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = req_id
    start_time = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Enforces consistent JSON error envelope across HTTP exceptions."""
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "details": {},
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Enforces consistent JSON error envelope for Pydantic validation failures."""
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed. Please check your request parameters.",
                "details": {"errors": exc.errors()},
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catches unhandled errors and returns sanitized error envelope."""
    req_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
                "request_id": req_id,
            }
        },
    )


@app.get("/healthz", tags=["System"])
async def healthz():
    """Liveness probe."""
    return {"status": "ok", "timestamp": time.time()}


@app.get("/readyz", tags=["System"])
async def readyz():
    """Readiness probe."""
    return {
        "status": "ready",
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "timestamp": time.time(),
    }


# Include Routers
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(facts_router)
app.include_router(resumes_router)
app.include_router(jobs_router)
app.include_router(matching_router)
app.include_router(applications_router)
