"""Central authentication dependency, re-auth check and HTTP concurrency helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Forbidden, PreconditionFailed, Unauthorized
from app.models import User
from app.security.ratelimit import enforce
from app.security.tokens import decode_access_token

ACCESS_COOKIE = "jp_access"
REFRESH_COOKIE = "jp_refresh"
CSRF_COOKIE = "jp_csrf"
CSRF_HEADER = "x-csrf-token"
REAUTH_WINDOW = timedelta(minutes=5)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise Unauthorized("Authentication required")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise Unauthorized("Authentication required")
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_recent_reauth(user: User) -> None:
    """Sensitive actions (export, deletion, integrations) need a password re-entry within 5 minutes."""
    if user.reauth_at is None or datetime.now(UTC) - user.reauth_at > REAUTH_WINDOW:
        raise Forbidden("Please re-enter your password to continue", code="reauth_required")


def rate_limit(bucket: str):  # type: ignore[no-untyped-def]
    async def _dep(request: Request) -> None:
        key = getattr(request.state, "user_id", None) or (request.client.host if request.client else "anon")
        enforce(bucket, key)

    return Depends(_dep)


def etag_for(version: int) -> str:
    return f'W/"{version}"'


def check_if_match(request: Request, version: int) -> None:
    """Optimistic concurrency: if If-Match is sent it must equal the current version ETag."""
    header = request.headers.get("if-match")
    if header is not None and header.strip() not in (etag_for(version), f'"{version}"', "*"):
        raise PreconditionFailed(
            "This item was changed elsewhere. Reload and try again.", details={"current_version": version}
        )


def parse_uuid(value: str) -> uuid.UUID:
    from app.errors import NotFound

    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise NotFound("Not found") from exc
