"""Registration, login with throttling/lockout, rotating refresh tokens, email verification,
password reset and re-authentication (spec §5)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import uuid7
from app.errors import Conflict, Unauthorized, UnprocessableError
from app.models import AuthToken, DevMailbox, User, UserProfile, UserSettings
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import create_access_token, hash_token, new_opaque_token

GENERIC_LOGIN_ERROR = "Invalid email or password"


@dataclass
class IssuedTokens:
    access: str
    refresh: str


def _now() -> datetime:
    return datetime.now(UTC)


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise UnprocessableError("Password must be at least 10 characters", code="weak_password")
    if password.lower() == password or not any(c.isdigit() for c in password):
        raise UnprocessableError("Password needs at least one uppercase letter and one digit", code="weak_password")


async def _issue_single_use(session: AsyncSession, user_id: uuid.UUID, kind: str, ttl: timedelta) -> str:
    token = new_opaque_token()
    session.add(AuthToken(user_id=user_id, kind=kind, token_hash=hash_token(token), expires_at=_now() + ttl))
    return token


async def _consume_single_use(session: AsyncSession, token: str, kind: str) -> AuthToken:
    row = (
        await session.execute(
            select(AuthToken).where(AuthToken.token_hash == hash_token(token), AuthToken.kind == kind)
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise UnprocessableError("This link is invalid or has expired", code="invalid_token")
    row.used_at = _now()
    return row


async def issue_session_tokens(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> IssuedTokens:
    refresh = new_opaque_token()
    session.add(
        AuthToken(
            user_id=user_id,
            kind="refresh",
            token_hash=hash_token(refresh),
            family_id=family_id or uuid7(),
            expires_at=_now() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    return IssuedTokens(access=create_access_token(user_id), refresh=refresh)


async def send_verification(session: AsyncSession, user: User) -> None:
    token = await _issue_single_use(session, user.id, "verify_email", timedelta(hours=24))
    session.add(
        DevMailbox(
            user_id=user.id,
            to_email=user.email,
            subject="Verify your JobPilot AI email",
            body=f"Open /verify-email?token={token} to verify your email address.",
        )
    )


async def register(session: AsyncSession, email: str, password: str) -> tuple[User, IssuedTokens]:
    email = email.strip().lower()
    validate_password_strength(password)
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        # Registration necessarily reveals an existing account; keep the message neutral.
        raise Conflict("Unable to register with this email. Try signing in or resetting your password.")
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    session.add(UserProfile(user_id=user.id))
    session.add(UserSettings(user_id=user.id))
    await send_verification(session, user)
    tokens = await issue_session_tokens(session, user.id)
    return user, tokens


async def login(session: AsyncSession, email: str, password: str) -> tuple[User, IssuedTokens]:
    settings = get_settings()
    email = email.strip().lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None and user.locked_until and user.locked_until > _now():
        verify_password(None, password)  # equalise timing
        raise Unauthorized(GENERIC_LOGIN_ERROR, code="invalid_credentials")
    if user is None or not verify_password(user.password_hash, password) or not user.is_active:
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.lockouts += 1
                backoff = settings.login_lockout_base_seconds * (2 ** (user.lockouts - 1))
                user.locked_until = _now() + timedelta(seconds=min(backoff, 3600))
                user.failed_login_count = 0
        raise Unauthorized(GENERIC_LOGIN_ERROR, code="invalid_credentials")
    user.failed_login_count = 0
    user.lockouts = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    tokens = await issue_session_tokens(session, user.id)
    return user, tokens


async def rotate_refresh(session: AsyncSession, refresh_token: str) -> tuple[uuid.UUID, IssuedTokens]:
    row = (
        await session.execute(
            select(AuthToken).where(AuthToken.token_hash == hash_token(refresh_token), AuthToken.kind == "refresh")
        )
    ).scalar_one_or_none()
    if row is None or row.expires_at < _now():
        raise Unauthorized("Session expired", code="session_expired")
    if row.used_at is not None:
        # Reuse of a rotated token => likely theft. Revoke the entire family.
        await session.execute(
            update(AuthToken)
            .where(AuthToken.family_id == row.family_id, AuthToken.used_at.is_(None))
            .values(used_at=_now())
        )
        await session.commit()
        raise Unauthorized("Session expired", code="session_expired")
    row.used_at = _now()
    tokens = await issue_session_tokens(session, row.user_id, family_id=row.family_id)
    return row.user_id, tokens


async def logout(session: AsyncSession, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    row = (
        await session.execute(select(AuthToken).where(AuthToken.token_hash == hash_token(refresh_token)))
    ).scalar_one_or_none()
    if row is not None and row.family_id is not None:
        await session.execute(
            update(AuthToken)
            .where(AuthToken.family_id == row.family_id, AuthToken.used_at.is_(None))
            .values(used_at=_now())
        )


async def verify_email(session: AsyncSession, token: str) -> None:
    row = await _consume_single_use(session, token, "verify_email")
    user = await session.get(User, row.user_id)
    if user is not None:
        user.email_verified = True


async def request_password_reset(session: AsyncSession, email: str) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    user = (await session.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
    if user is None:
        return
    token = await _issue_single_use(session, user.id, "reset_password", timedelta(hours=1))
    session.add(
        DevMailbox(
            user_id=user.id,
            to_email=user.email,
            subject="Reset your JobPilot AI password",
            body=f"Open /reset-password?token={token} to choose a new password. Expires in 1 hour.",
        )
    )


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    validate_password_strength(new_password)
    row = await _consume_single_use(session, token, "reset_password")
    user = await session.get(User, row.user_id)
    if user is None:
        raise UnprocessableError("This link is invalid or has expired", code="invalid_token")
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    # Invalidate all existing sessions.
    await session.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.kind == "refresh", AuthToken.used_at.is_(None))
        .values(used_at=_now())
    )


async def reauthenticate(user: User, password: str) -> None:
    if not verify_password(user.password_hash, password):
        raise Unauthorized("Password is incorrect", code="invalid_credentials")
    user.reauth_at = _now()
