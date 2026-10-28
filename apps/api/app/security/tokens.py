"""Access tokens (short-lived JWT) and opaque single-use tokens (stored hashed)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = cast(dict[str, Any], jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM]))
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    try:
        return uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        return None


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)
