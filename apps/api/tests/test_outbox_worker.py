"""Outbox/worker semantics: retries with backoff, dead letters, idempotent duplicate delivery, reminders."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import Job, JobMatch, Notification, OutboxEvent, Reminder, User
from app.services import tasks
from app.services.platform import emit
from tests.conftest import FIXTURES, Api, onboard


async def _uid() -> uuid.UUID:
    async with get_sessionmaker()() as s:
        return (await s.execute(select(User.id))).scalar_one()


async def test_duplicate_delivery_is_harmless(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    await onboard(api)
    monkeypatch.setattr(get_settings(), "inline_tasks", False)
    r = await api.post("/api/jobs/import/manual_paste", {"text": (FIXTURES / "job_ml_engineer.txt").read_text("utf-8")})
    job_id = uuid.UUID(r.json()["created"][0]["id"])
    uid = await _uid()
    async with get_sessionmaker()() as s:
        assert (await s.execute(select(func.count()).select_from(JobMatch))).scalar_one() == 0  # not processed yet
        ev = (await s.execute(select(OutboxEvent).where(OutboxEvent.kind == "job.ingested"))).scalar_one()
        # simulate redelivery: run the handler twice
        await tasks.handle(s, ev)
        await tasks.handle(s, ev)
        await tasks.process_outbox(s)
        await s.commit()
        assert (
            await s.execute(select(func.count()).select_from(JobMatch).where(JobMatch.job_id == job_id))
        ).scalar_one() == 1
        await emit(s, uid, "job.ingested", {"user_id": str(uid), "job_id": str(job_id)}, f"job.ingested:{job_id}")
        await s.commit()
        assert (
            await s.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.kind == "job.ingested"))
        ).scalar_one() == 1


async def test_failing_event_retries_then_dead_letters(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    uid = await _uid()

    async def boom(session, event):  # type: ignore[no-untyped-def]
        raise RuntimeError("downstream unavailable")

    monkeypatch.setattr(tasks, "handle", boom)
    async with get_sessionmaker()() as s:
        await emit(s, uid, "notify", {"user_id": str(uid), "message": "x"}, "evt-fail-1")
        await s.commit()
        for _ in range(tasks.MAX_ATTEMPTS):
            ev = (await s.execute(select(OutboxEvent).where(OutboxEvent.dedupe_key == "evt-fail-1"))).scalar_one()
            ev.next_attempt_at = None  # skip the backoff wait
            await tasks.process_outbox(s)
        ev = (await s.execute(select(OutboxEvent).where(OutboxEvent.dedupe_key == "evt-fail-1"))).scalar_one()
        assert ev.dead and ev.attempts == tasks.MAX_ATTEMPTS and "downstream unavailable" in ev.last_error


async def test_backoff_delays_retry(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    uid = await _uid()
    calls = 0

    async def flaky(session, event):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        raise RuntimeError("x")

    monkeypatch.setattr(tasks, "handle", flaky)
    async with get_sessionmaker()() as s:
        await emit(s, uid, "notify", {"user_id": str(uid), "message": "x"}, "evt-backoff")
        await tasks.process_outbox(s)
        await tasks.process_outbox(s)  # still in backoff window -> not retried
        assert calls == 1
        ev = (await s.execute(select(OutboxEvent).where(OutboxEvent.dedupe_key == "evt-backoff"))).scalar_one()
        assert ev.next_attempt_at is not None and ev.next_attempt_at > datetime.now(UTC)


async def test_due_reminders_create_single_notification(api: Api) -> None:
    uid = await _uid()
    async with get_sessionmaker()() as s:
        s.add(Reminder(user_id=uid, due_at=datetime.now(UTC) - timedelta(minutes=1), message="Follow up with Acme"))
        s.add(Reminder(user_id=uid, due_at=datetime.now(UTC) + timedelta(days=3), message="Later"))
        await s.commit()
        assert await tasks.due_reminders(s) == 1
        assert await tasks.due_reminders(s) == 0
        await s.commit()
    notes = (await api.get("/api/notifications")).json()
    assert [n["message"] for n in notes] == ["Follow up with Acme"]
    await api.post("/api/notifications/read-all")
    assert (await api.get("/api/notifications", params={"unread_only": True})).json() == []


async def test_worker_iteration_runs(api: Api) -> None:
    async with get_sessionmaker()() as s:
        await tasks.process_outbox(s)
        await tasks.reverify_stale(s)
        await tasks.apply_retention(s)
        await s.commit()
    async with get_sessionmaker()() as s:
        assert (await s.execute(select(func.count()).select_from(Notification))).scalar_one() >= 0
        assert (await s.execute(select(func.count()).select_from(Job))).scalar_one() == 0
