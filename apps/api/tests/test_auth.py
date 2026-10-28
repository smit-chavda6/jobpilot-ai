import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.db import get_sessionmaker
from app.models import AuthToken, User
from tests.conftest import PASSWORD, Api


async def _mail_token(api: Api, email: str, kind: str) -> str:
    mails = (await api.get("/api/auth/dev-mailbox", params={"email": email})).json()
    body = next(m["body"] for m in mails if kind in m["body"])
    return re.search(r"token=([\w-]+)", body).group(1)  # type: ignore[union-attr]


async def test_register_login_me_logout(make_api) -> None:  # type: ignore[no-untyped-def]
    api: Api = await make_api("bob@example.com")
    me = (await api.get("/api/auth/me")).json()
    assert me["email"] == "bob@example.com" and me["email_verified"] is False
    assert (await api.post("/api/auth/logout")).status_code == 200
    assert (await api.get("/api/auth/me")).status_code == 401
    r = await api.post("/api/auth/login", {"email": "BOB@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert (await api.get("/api/auth/me")).status_code == 200


async def test_cookies_are_httponly(make_api) -> None:  # type: ignore[no-untyped-def]
    api: Api = await make_api()
    r = await api.post("/api/auth/register", {"email": "c@example.com", "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("jp_access="))
    refresh = next(c for c in cookies if c.startswith("jp_refresh="))
    assert "HttpOnly" in access and "samesite=lax" in access.lower()
    assert "HttpOnly" in refresh and "samesite=strict" in refresh.lower()


async def test_weak_password_rejected(anon: Api) -> None:
    r = await anon.post("/api/auth/register", {"email": "w@example.com", "password": "short"})
    assert r.status_code == 422


async def test_duplicate_registration(make_api) -> None:  # type: ignore[no-untyped-def]
    await make_api("dup@example.com")
    other: Api = await make_api()
    r = await other.post("/api/auth/register", {"email": "dup@example.com", "password": PASSWORD})
    assert r.status_code == 409


async def test_generic_login_errors_no_enumeration(make_api) -> None:  # type: ignore[no-untyped-def]
    await make_api("known@example.com")
    anon: Api = await make_api()
    wrong = await anon.post("/api/auth/login", {"email": "known@example.com", "password": "Wrong1Password"})
    missing = await anon.post("/api/auth/login", {"email": "nobody@example.com", "password": "Wrong1Password"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["error"]["message"] == missing.json()["error"]["message"]


async def test_lockout_after_failed_attempts(make_api) -> None:  # type: ignore[no-untyped-def]
    await make_api("lock@example.com")
    anon: Api = await make_api()
    for _ in range(5):
        await anon.post("/api/auth/login", {"email": "lock@example.com", "password": "Wrong1Password"})
    # Even the correct password is refused while locked, with the same generic message.
    r = await anon.post("/api/auth/login", {"email": "lock@example.com", "password": PASSWORD})
    assert r.status_code == 401
    async with get_sessionmaker()() as s:
        user = (await s.execute(select(User).where(User.email == "lock@example.com"))).scalar_one()
        assert user.locked_until is not None and user.locked_until > datetime.now(UTC)
        await s.execute(
            update(User).where(User.id == user.id).values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    assert (await anon.post("/api/auth/login", {"email": "lock@example.com", "password": PASSWORD})).status_code == 200


async def test_refresh_rotation_and_reuse_detection(api: Api) -> None:
    old_refresh = api.c.cookies.get("jp_refresh")
    assert (await api.post("/api/auth/refresh")).status_code == 200
    new_refresh = api.c.cookies.get("jp_refresh")
    assert new_refresh and new_refresh != old_refresh
    # Replaying the rotated token revokes the whole family.
    api.c.cookies.set("jp_refresh", old_refresh, path="/api/auth")  # type: ignore[arg-type]
    assert (await api.post("/api/auth/refresh")).status_code == 401
    api.c.cookies.set("jp_refresh", new_refresh, path="/api/auth")
    assert (await api.post("/api/auth/refresh")).status_code == 401


async def test_email_verification_single_use(api: Api) -> None:
    token = await _mail_token(api, "alice@example.com", "verify-email")
    assert (await api.post("/api/auth/verify-email", {"token": token})).status_code == 200
    assert (await api.get("/api/auth/me")).json()["email_verified"] is True
    assert (await api.post("/api/auth/verify-email", {"token": token})).status_code == 422


async def test_password_reset_flow(make_api) -> None:  # type: ignore[no-untyped-def]
    await make_api("reset@example.com")
    anon: Api = await make_api()
    r = await anon.post("/api/auth/forgot-password", {"email": "reset@example.com"})
    assert r.status_code == 202
    r2 = await anon.post("/api/auth/forgot-password", {"email": "ghost@example.com"})
    assert r2.status_code == 202 and r2.json() == r.json()
    token = await _mail_token(anon, "reset@example.com", "reset-password")
    assert (
        await anon.post("/api/auth/reset-password", {"token": token, "password": "N3wPassword!!"})
    ).status_code == 200
    assert (
        await anon.post("/api/auth/reset-password", {"token": token, "password": "Other3Password"})
    ).status_code == 422
    assert (
        await anon.post("/api/auth/login", {"email": "reset@example.com", "password": "N3wPassword!!"})
    ).status_code == 200


async def test_expired_reset_token_rejected(make_api) -> None:  # type: ignore[no-untyped-def]
    await make_api("exp@example.com")
    anon: Api = await make_api()
    await anon.post("/api/auth/forgot-password", {"email": "exp@example.com"})
    token = await _mail_token(anon, "exp@example.com", "reset-password")
    async with get_sessionmaker()() as s:
        await s.execute(
            update(AuthToken)
            .where(AuthToken.kind == "reset_password")
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await s.commit()
    assert (
        await anon.post("/api/auth/reset-password", {"token": token, "password": "N3wPassword!!"})
    ).status_code == 422


async def test_reauth_required_for_sensitive_actions(api: Api) -> None:
    r = await api.post("/api/privacy/export")
    assert r.status_code == 403 and r.json()["error"]["code"] == "reauth_required"
    assert (await api.post("/api/auth/reauth", {"password": "Wrong1Password"})).status_code == 401
    assert (await api.post("/api/auth/reauth", {"password": PASSWORD})).status_code == 200
    assert (await api.post("/api/privacy/export")).status_code == 200


async def test_tokens_stored_hashed(api: Api) -> None:
    raw = api.c.cookies.get("jp_refresh")
    async with get_sessionmaker()() as s:
        hashes = (await s.execute(select(AuthToken.token_hash))).scalars().all()
    assert raw not in hashes and all(len(h) == 64 for h in hashes)
