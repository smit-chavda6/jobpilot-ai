from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="jobpilot-test-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'boot.db').as_posix()}",
        "JWT_SECRET": "test-secret-test-secret-test-secret-test-secret",
        "ENCRYPTION_KEY": "0Q1xKk8m1z6mX3cF4C7xg0bQ7XcH9vR2y5k3oW8sJpU=",
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "INLINE_TASKS": "true",
        "LLM_PROVIDER": "mock",
        "CORS_ORIGINS": "http://localhost:5173",
    }
)

import httpx  # noqa: E402

from app import db as app_db  # noqa: E402
from app import models as _models  # noqa: E402,F401  (registers tables on Base.metadata)
from app.ai.providers import set_provider  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.security.ratelimit import limiter  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "Sup3rSecurePass"


# Set TEST_DATABASE_URL (e.g. postgresql+asyncpg://...) to run the suite against a real Postgres;
# every test then starts from freshly dropped and recreated tables. Default: a per-test SQLite file.
PG_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path: Path) -> AsyncIterator[None]:
    os.environ["DATABASE_URL"] = PG_URL or f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    os.environ["UPLOAD_DIR"] = str(tmp_path / "uploads")
    get_settings.cache_clear()
    await app_db.reset_engine()
    async with app_db.get_engine().begin() as conn:
        if PG_URL:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    limiter.reset()
    set_provider(None)
    yield
    set_provider(None)
    await app_db.reset_engine()


class Api:
    """Thin test client that manages the CSRF double-submit token like the SPA does."""

    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.csrf = ""

    async def init(self) -> Api:
        r = await self.c.get("/api/auth/csrf")
        self.csrf = r.json()["csrf_token"]
        return self

    def _h(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf, **(extra or {})}

    async def get(self, url: str, **kw: object) -> httpx.Response:
        return await self.c.get(url, **kw)  # type: ignore[arg-type]

    async def post(
        self, url: str, json: object = None, headers: dict[str, str] | None = None, **kw: object
    ) -> httpx.Response:
        return await self.c.post(url, json=json, headers=self._h(headers), **kw)  # type: ignore[arg-type]

    async def put(self, url: str, json: object = None, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.c.put(url, json=json, headers=self._h(headers))

    async def patch(self, url: str, json: object = None, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.c.patch(url, json=json, headers=self._h(headers))

    async def delete(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.c.delete(url, headers=self._h(headers))

    async def upload(
        self, url: str, filename: str, data: bytes, mime: str = "application/octet-stream"
    ) -> httpx.Response:
        return await self.c.post(url, files={"file": (filename, data, mime)}, headers=self._h())


def _app():  # type: ignore[no-untyped-def]
    from app.main import create_app

    return create_app()


@pytest.fixture
async def make_api() -> AsyncIterator[object]:
    clients: list[httpx.AsyncClient] = []
    app = _app()

    async def factory(email: str | None = None, password: str = PASSWORD) -> Api:
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        api = await Api(client).init()
        if email:
            r = await api.post("/api/auth/register", {"email": email, "password": password})
            assert r.status_code == 201, r.text
        return api

    yield factory
    for c in clients:
        await c.aclose()


@pytest.fixture
async def api(make_api) -> Api:  # type: ignore[no-untyped-def]
    return await make_api("alice@example.com")


@pytest.fixture
async def anon(make_api) -> Api:  # type: ignore[no-untyped-def]
    return await make_api()


async def onboard(api: Api, resume_name: str = "resume_alex.txt") -> list[dict[str, object]]:
    """Upload the fixture resume, confirm all facts and set preferences. Returns confirmed facts."""
    await api.post("/api/consents", {"purpose": "ai_processing", "granted": True})
    r = await api.patch(
        "/api/profile",
        {
            "full_name": "Alex Rivera",
            "headline": "Data Scientist",
            "location": "Bengaluru, India",
            "years_experience": 4,
            "education_level": "master",
            "target_titles": ["Data Scientist", "ML Engineer"],
            "preferred_locations": ["Bengaluru", "Remote"],
            "remote_preference": "any",
            "employment_types": ["full_time"],
            "onboarding_completed": True,
        },
    )
    assert r.status_code == 200, r.text
    data = (FIXTURES / resume_name).read_bytes()
    r = await api.upload("/api/resumes", resume_name, data, "text/plain")
    assert r.status_code == 201, r.text
    ids = [f["id"] for f in r.json()["facts"]]
    r = await api.post("/api/facts/status", {"fact_ids": ids, "status": "confirmed"})
    assert r.status_code == 200, r.text
    return r.json()
