"""Cross-cutting services: audit log, transactional outbox, idempotency keys."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict
from app.logging_setup import request_id_var
from app.models import AuditLog, IdempotencyRecord, OutboxEvent


def audit(
    session: AsyncSession,
    user_id: uuid.UUID | None,
    action: str,
    target: str = "",
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target=target,
            detail=detail or {},
            ip=request.client.host if request and request.client else None,
            request_id=request_id_var.get(),
        )
    )


async def emit(
    session: AsyncSession, user_id: uuid.UUID | None, kind: str, payload: dict[str, Any], dedupe_key: str
) -> None:
    """Write an outbox event in the caller's transaction. Duplicate dedupe keys are ignored."""
    exists = (
        await session.execute(select(OutboxEvent.id).where(OutboxEvent.dedupe_key == dedupe_key))
    ).scalar_one_or_none()
    if exists is None:
        session.add(OutboxEvent(user_id=user_id, kind=kind, payload=payload, dedupe_key=dedupe_key))


def _request_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


async def idempotent_lookup(
    session: AsyncSession, user_id: uuid.UUID, key: str | None, endpoint: str, body: Any
) -> IdempotencyRecord | None:
    if not key:
        return None
    rec = (
        await session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.key == key,
                IdempotencyRecord.endpoint == endpoint,
            )
        )
    ).scalar_one_or_none()
    if rec is not None and rec.request_hash != _request_hash(body):
        raise Conflict("Idempotency-Key was reused with a different request body", code="idempotency_mismatch")
    return rec


def idempotent_store(
    session: AsyncSession,
    user_id: uuid.UUID,
    key: str | None,
    endpoint: str,
    body: Any,
    status_code: int,
    response: Any,
) -> None:
    if key:
        session.add(
            IdempotencyRecord(
                user_id=user_id,
                key=key,
                endpoint=endpoint,
                request_hash=_request_hash(body),
                status_code=status_code,
                response=json.loads(json.dumps(response, default=str)),
            )
        )
