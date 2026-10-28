from tests.conftest import Api


async def test_healthz_and_readyz(anon: Api) -> None:
    assert (await anon.get("/healthz")).json() == {"status": "ok"}
    r = await anon.get("/readyz")
    assert r.status_code == 200 and r.json()["database"] == "ok"


async def test_security_headers_and_request_id(anon: Api) -> None:
    r = await anon.get("/api/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


async def test_csrf_required_for_state_changes(anon: Api) -> None:
    r = await anon.c.post("/api/auth/register", json={"email": "x@example.com", "password": "Sup3rSecurePass"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    r = await anon.c.post(
        "/api/auth/register",
        json={"email": "x@example.com", "password": "Sup3rSecurePass"},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert r.status_code == 403


async def test_error_envelope_shape(api: Api) -> None:
    r = await api.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    body = r.json()
    assert r.status_code == 404
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"]


async def test_validation_errors_use_envelope(api: Api) -> None:
    r = await api.patch("/api/profile", {"years_experience": -5})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_unauthenticated_is_401(anon: Api) -> None:
    for path in ("/api/profile", "/api/jobs", "/api/applications", "/api/analytics"):
        assert (await anon.get(path)).status_code == 401, path


async def test_cors_allowlist(anon: Api) -> None:
    ok = await anon.c.options(
        "/api/auth/csrf", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = await anon.c.options(
        "/api/auth/csrf", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in bad.headers


async def test_logs_redact_pii() -> None:
    from app.logging_setup import redact

    out = redact("user alex.rivera@example.com phone +91 98765 43210 key sk-abcdefghijklmnop password=hunter22")
    assert "example.com" not in out and "98765" not in out and "sk-abc" not in out and "hunter22" not in out
