"""Automated authorization sweep (spec §5): every private endpoint, called by another user with the
victim's resource IDs, must return 403/404 and must not change or leak the victim's data."""

import re

from fastapi.routing import APIRoute
from sqlalchemy import select

from app.db import get_sessionmaker
from app.main import create_app
from app.models import User, UserIntegration
from tests.conftest import FIXTURES, Api, onboard

PUBLIC = {
    "/api/auth/csrf",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/verify-email",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/dev-mailbox",
    "/healthz",
    "/readyz",
    "/api/healthz",
    "/api/readyz",
}
NOT_OWNED_PARAMS = {"source"}  # import source id and adapter id are global registry keys, not user resources

BODIES: dict[tuple[str, str], object] = {
    ("POST", "/api/jobs/{job_id}/scam-feedback"): {"signal_code": "upfront_fee"},
    ("PATCH", "/api/facts/{fact_id}"): {"text": "Hijacked fact"},
    ("PUT", "/api/documents/{doc_id}"): {"items": []},
    ("PATCH", "/api/applications/{app_id}/notes"): {"notes": "x"},
    ("PUT", "/api/applications/{app_id}/documents"): {},
    ("POST", "/api/applications/{app_id}/approve"): {"payload_hash": "0" * 64},
    ("POST", "/api/applications/{app_id}/confirm-submission"): {"confirmed": True},
    ("POST", "/api/applications/{app_id}/move"): {"status": "withdrawn"},
    ("POST", "/api/applications/{app_id}/screening"): {"question": "Do you know Python?"},
    ("PUT", "/api/applications/{app_id}/screening/{answer_id}"): {"answer": "x"},
    ("POST", "/api/applications/{app_id}/reminders"): {"due_at": "2026-12-01T00:00:00Z", "message": "x"},
    ("POST", "/api/interview-prep/sessions/{session_id}/answers"): {"question_id": "q1", "answer": "x"},
    ("PUT", "/api/sources/{source_id}"): {"enabled": False},
}


async def _victim(api: Api) -> dict[str, str]:
    await onboard(api)
    job_id = (
        await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    ).json()["created"][0]["id"]
    await api.upload("/api/jobs/import/file", "jobs.csv", (FIXTURES / "jobs.csv").read_bytes(), "text/csv")
    app_id = (await api.post("/api/applications", {"job_id": job_id})).json()["id"]
    await api.post(f"/api/applications/{app_id}/prepare")
    app = (await api.get(f"/api/applications/{app_id}")).json()
    app = (await api.post(f"/api/applications/{app_id}/screening", {"question": "Why us?"})).json()
    reminder = (
        await api.post(f"/api/applications/{app_id}/reminders", {"due_at": "2026-12-01T00:00:00Z", "message": "r"})
    ).json()
    email = (await api.upload("/api/triage/upload", "i.eml", (FIXTURES / "email_interview.eml").read_bytes())).json()[0]
    session = (await api.post("/api/interview-prep/sessions", {"job_id": job_id})).json()
    facts = (await api.get("/api/facts")).json()
    resumes = (await api.get("/api/resumes")).json()
    failed = (await api.get("/api/jobs/failed-imports")).json()
    async with get_sessionmaker()() as s:
        uid = (await s.execute(select(User.id).where(User.email == "alice@example.com"))).scalar_one()
        integ = UserIntegration(user_id=uid, provider="gmail", scopes=["r"], token_encrypted="x")
        s.add(integ)
        await s.commit()
        integ_id = str(integ.id)
    return {
        "job_id": job_id,
        "app_id": app_id,
        "doc_id": app["resume_doc_id"],
        "fact_id": facts[0]["id"],
        "resume_id": resumes[0]["id"],
        "email_id": email["id"],
        "session_id": session["id"],
        "reminder_id": reminder["id"],
        "answer_id": app["screening"][0]["id"],
        "item_id": failed[0]["id"],
        "integration_id": integ_id,
        "source_id": "greenhouse",
    }


async def test_cross_tenant_sweep(api: Api, make_api) -> None:  # type: ignore[no-untyped-def]
    ids = await _victim(api)
    before_app = (await api.get(f"/api/applications/{ids['app_id']}")).json()
    before_facts = (await api.get("/api/facts")).json()
    attacker: Api = await make_api("mallory@example.com")
    await attacker.post("/api/auth/reauth", {"password": "Sup3rSecurePass"})

    checked = 0
    for route in create_app().routes:
        if not isinstance(route, APIRoute) or "{" not in route.path:
            continue
        params = re.findall(r"{(\w+)}", route.path)
        if set(params) & NOT_OWNED_PARAMS or route.path == "/api/sources/{source_id}":
            continue
        url = route.path
        for p in params:
            url = url.replace("{" + p + "}", ids[p])
        for method in route.methods - {"HEAD", "OPTIONS"}:
            body = BODIES.get((method, route.path))
            if method == "GET":
                r = await attacker.get(url)
            elif method == "DELETE":
                r = await attacker.delete(url)
            else:
                r = await attacker.c.request(method, url, json=body, headers={"X-CSRF-Token": attacker.csrf})
            assert r.status_code in (403, 404), (method, route.path, r.status_code, r.text[:200])
            for v in ids.values():
                if v != "greenhouse":
                    assert v not in r.text, (method, route.path, "leaked id")
            checked += 1
    assert checked >= 30

    # IDs smuggled through bodies / query strings
    body_cases = [
        ("POST", "/api/applications", {"job_id": ids["job_id"]}),
        ("POST", "/api/documents", {"kind": "resume", "job_id": ids["job_id"]}),
        ("POST", "/api/facts/status", {"fact_ids": [ids["fact_id"]], "status": "rejected"}),
        ("POST", "/api/jobs/bulk", {"job_ids": [ids["job_id"]], "action": "archive"}),
        ("POST", "/api/interview-prep/star", {"question": "Tell me", "job_id": ids["job_id"]}),
        ("POST", "/api/interview-prep/sessions", {"job_id": ids["job_id"]}),
    ]
    for method, url, body in body_cases:
        r = await attacker.c.request(method, url, json=body, headers={"X-CSRF-Token": attacker.csrf})
        assert r.status_code == 404, (url, r.status_code, r.text[:200])
    assert (await attacker.get("/api/interview-prep/bank", params={"job_id": ids["job_id"]})).status_code == 404

    # Attacker's own lists are empty
    assert (await attacker.get("/api/jobs")).json()["items"] == []
    assert (await attacker.get("/api/facts")).json() == []
    assert (await attacker.get("/api/documents", params={"job_id": ids["job_id"]})).json() == []

    # Victim's data unchanged
    after_app = (await api.get(f"/api/applications/{ids['app_id']}")).json()
    assert after_app["status"] == before_app["status"] and after_app["version"] == before_app["version"]
    assert (await api.get("/api/facts")).json() == before_facts


async def test_every_private_route_requires_auth(anon: Api) -> None:
    for route in create_app().routes:
        if not isinstance(route, APIRoute) or route.path in PUBLIC or not route.path.startswith("/api"):
            continue
        url = re.sub(r"{\w+}", "00000000-0000-0000-0000-000000000000", route.path)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = await anon.c.request(method, url, json={}, headers={"X-CSRF-Token": anon.csrf})
            assert r.status_code in (401, 422), (method, route.path, r.status_code)
            if r.status_code == 422:
                # validation may run first, but a valid request must still be refused
                assert r.json()["error"]["code"] == "validation_error"
