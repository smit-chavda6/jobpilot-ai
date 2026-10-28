"""Idempotency-Key handling shared by POST endpoints that create resources or trigger AI generation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.platform import idempotent_lookup, idempotent_store


async def idempotent(
    request: Request,
    session: AsyncSession,
    user: User,
    endpoint: str,
    body: Any,
    fn: Callable[[], Awaitable[Any]],
    status_code: int = 201,
) -> JSONResponse:
    key = request.headers.get("idempotency-key")
    if key is not None and not (8 <= len(key) <= 128):
        key = None
    existing = await idempotent_lookup(session, user.id, key, endpoint, body)
    if existing is not None:
        return JSONResponse(
            existing.response, status_code=existing.status_code, headers={"Idempotent-Replayed": "true"}
        )
    result = jsonable_encoder(await fn())
    idempotent_store(session, user.id, key, endpoint, body, status_code, result)
    return JSONResponse(result, status_code=status_code)
