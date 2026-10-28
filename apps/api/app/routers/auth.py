from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.config import get_settings
from app.errors import NotFound, Unauthorized
from app.models import DevMailbox, User
from app.security.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    SessionDep,
    rate_limit,
)
from app.security.tokens import new_csrf_token
from app.services import auth_service
from app.services.platform import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetIn(TokenIn):
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    email_verified: bool


def _user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, email_verified=user.email_verified)


def _set_session_cookies(response: Response, tokens: auth_service.IssuedTokens) -> None:
    s = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.access_token_minutes * 60,
        path="/api",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        max_age=s.refresh_token_days * 86400,
        path="/api/auth",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@router.get("/csrf")
async def csrf(request: Request, response: Response) -> dict[str, str]:
    """Issue (or re-use) the double-submit CSRF token. The SPA sends it back as X-CSRF-Token."""
    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE, token, httponly=False, secure=get_settings().cookie_secure, samesite="strict", path="/"
    )
    return {"csrf_token": token}


@router.post("/register", status_code=201, dependencies=[rate_limit("auth")])
async def register(body: Credentials, request: Request, response: Response, session: SessionDep) -> UserOut:
    user, tokens = await auth_service.register(session, body.email, body.password)
    audit(session, user.id, "auth.register", request=request)
    _set_session_cookies(response, tokens)
    return _user_out(user)


@router.post("/login", dependencies=[rate_limit("auth")])
async def login(body: Credentials, request: Request, response: Response, session: SessionDep) -> UserOut:
    try:
        user, tokens = await auth_service.login(session, body.email, body.password)
    except Unauthorized:
        await session.commit()  # persist failed-attempt counters
        raise
    audit(session, user.id, "auth.login", request=request)
    _set_session_cookies(response, tokens)
    return _user_out(user)


@router.post("/refresh", dependencies=[rate_limit("auth")])
async def refresh(request: Request, response: Response, session: SessionDep) -> dict[str, bool]:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthorized("Session expired", code="session_expired")
    try:
        _, tokens = await auth_service.rotate_refresh(session, token)
    except Unauthorized:
        _clear_session_cookies(response)
        raise
    _set_session_cookies(response, tokens)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response, session: SessionDep) -> dict[str, bool]:
    await auth_service.logout(session, request.cookies.get(REFRESH_COOKIE))
    _clear_session_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.post("/verify-email")
async def verify_email(body: TokenIn, session: SessionDep) -> dict[str, bool]:
    await auth_service.verify_email(session, body.token)
    return {"ok": True}


@router.post("/request-verification", dependencies=[rate_limit("auth")])
async def request_verification(user: CurrentUser, session: SessionDep) -> dict[str, bool]:
    if not user.email_verified:
        await auth_service.send_verification(session, user)
    return {"ok": True}


@router.post("/forgot-password", status_code=202, dependencies=[rate_limit("auth")])
async def forgot_password(body: EmailIn, session: SessionDep) -> dict[str, str]:
    await auth_service.request_password_reset(session, body.email)
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetIn, session: SessionDep) -> dict[str, bool]:
    await auth_service.reset_password(session, body.token, body.password)
    return {"ok": True}


@router.post("/reauth", dependencies=[rate_limit("auth")])
async def reauth(body: PasswordIn, user: CurrentUser, request: Request, session: SessionDep) -> dict[str, bool]:
    await auth_service.reauthenticate(user, body.password)
    audit(session, user.id, "auth.reauth", request=request)
    return {"ok": True}


@router.get("/dev-mailbox")
async def dev_mailbox(email: EmailStr, session: SessionDep) -> list[dict[str, str]]:
    """Development-only: read transactional emails (verification / reset) that would be sent."""
    if get_settings().app_env == "production":
        raise NotFound("Not found")
    rows = (
        (
            await session.execute(
                select(DevMailbox).where(DevMailbox.to_email == email.lower()).order_by(DevMailbox.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [{"subject": r.subject, "body": r.body, "created_at": r.created_at.isoformat()} for r in rows[:20]]
