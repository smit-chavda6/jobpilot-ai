"""Background task handlers driven by the transactional outbox.

Handlers are idempotent so duplicate delivery is harmless. In development (`INLINE_TASKS=true`) the
API drains a user's events at the end of the request; in Compose the worker container does it.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AIUsageLog, Job, Notification, OutboxEvent, Reminder, UserSettings
from app.repositories import Repo
from app.services import ingestion, match_service

log = logging.getLogger("jobpilot.tasks")
MAX_ATTEMPTS = 5


async def _notify(session: AsyncSession, payload: dict[str, Any], dedupe: str) -> None:
    user_id = uuid.UUID(payload["user_id"])
    exists = await Repo(session, Notification, user_id).find(Notification.dedupe_key == dedupe)
    if exists is None:
        session.add(
            Notification(
                user_id=user_id,
                kind=payload.get("kind", "info"),
                message=payload["message"][:500],
                link=payload.get("link"),
                dedupe_key=dedupe,
            )
        )


async def handle(session: AsyncSession, event: OutboxEvent) -> None:
    p = event.payload
    if event.kind == "job.ingested":
        user_id = uuid.UUID(p["user_id"])
        job = await Repo(session, Job, user_id).find(Job.id == uuid.UUID(p["job_id"]))
        if job is not None:
            await match_service.score_jobs(session, user_id, [job])
    elif event.kind == "matches.rescore":
        await match_service.score_jobs(session, uuid.UUID(p["user_id"]))
    elif event.kind == "notify":
        await _notify(session, p, event.dedupe_key)
    else:
        log.warning("unknown outbox event kind=%s", event.kind)


async def process_outbox(session: AsyncSession, user_id: uuid.UUID | None = None, limit: int = 100) -> int:
    now = datetime.now(UTC)
    q = (
        select(OutboxEvent)
        .where(
            OutboxEvent.processed_at.is_(None),
            OutboxEvent.dead.is_(False),
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    if user_id is not None:
        q = q.where(OutboxEvent.user_id == user_id)
    events = list((await session.execute(q)).scalars().all())
    # Collapse redundant rescore events: one full rescore covers them all.
    seen_rescore: set[str] = set()
    done = 0
    for ev in events:
        if ev.kind == "matches.rescore":
            key = ev.payload.get("user_id", "")
            if key in seen_rescore:
                ev.processed_at = now
                continue
            seen_rescore.add(key)
        try:
            async with session.begin_nested():
                await handle(session, ev)
            ev.processed_at = datetime.now(UTC)
            done += 1
        except (IntegrityError, Exception) as exc:  # noqa: BLE001 - recorded and retried with backoff
            ev.attempts += 1
            ev.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            if ev.attempts >= MAX_ATTEMPTS:
                ev.dead = True
            else:
                backoff = 2**ev.attempts
                ev.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff + random.uniform(0, backoff))
            log.warning("outbox event failed kind=%s attempts=%s", ev.kind, ev.attempts)
    await session.flush()
    return done


async def run_inline(session: AsyncSession, user_id: uuid.UUID) -> None:
    if get_settings().inline_tasks:
        await process_outbox(session, user_id)


async def due_reminders(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    rows = (
        (
            await session.execute(
                select(Reminder)
                .where(Reminder.done.is_(False), Reminder.notified.is_(False), Reminder.due_at <= now)
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    for r in rows:
        s = (await session.execute(select(UserSettings).where(UserSettings.user_id == r.user_id))).scalar_one_or_none()
        if s is None or s.notify_reminders:
            await _notify(
                session,
                {
                    "user_id": str(r.user_id),
                    "kind": "reminder",
                    "message": r.message,
                    "link": f"/applications/{r.application_id}" if r.application_id else None,
                },
                f"reminder:{r.id}",
            )
        r.notified = True
    return len(rows)


async def reverify_stale(session: AsyncSession, max_jobs: int = 20) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=3)
    rows = (
        (
            await session.execute(
                select(Job)
                .where(
                    Job.archived.is_(False),
                    Job.url.is_not(None),
                    Job.is_demo.is_(False),
                    or_(Job.last_seen_at.is_(None), Job.last_seen_at < cutoff),
                    Job.verification_status.in_(("verified_live", "unverified")),
                )
                .limit(max_jobs)
            )
        )
        .scalars()
        .all()
    )
    for job in rows:
        await ingestion.reverify(session, job.user_id, job)
    return len(rows)


async def apply_retention(session: AsyncSession) -> None:
    rows = (await session.execute(select(UserSettings).where(UserSettings.retention_days.is_not(None)))).scalars().all()
    for s in rows:
        cutoff = datetime.now(UTC) - timedelta(days=int(s.retention_days or 0))
        await session.execute(delete(AIUsageLog).where(AIUsageLog.user_id == s.user_id, AIUsageLog.created_at < cutoff))
        await session.execute(
            delete(OutboxEvent).where(
                OutboxEvent.user_id == s.user_id, OutboxEvent.processed_at.is_not(None), OutboxEvent.created_at < cutoff
            )
        )
