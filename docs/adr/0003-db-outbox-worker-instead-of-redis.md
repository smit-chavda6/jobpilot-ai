# ADR-0003: Database outbox and polling worker instead of Redis/Celery

- **Status:** accepted · 2026-10-28

## Context
The spec suggests Redis with Celery or Arq. The workload is small (one person's imports, reminders, re-verification) and must be crash-safe and idempotent.

## Decision
Events are written to an `outbox_events` table in the same transaction as the change that causes them. `python -m app.worker` polls every 2 s, processes events idempotently and marks them done. Periodic jobs (reminders, listing re-verification, retention) run every 60 s. `INLINE_TASKS=true` processes the outbox inside the request for local dev and tests. No Redis service is shipped.

## Consequences
One fewer moving part, and no event can be lost between the DB commit and a broker. Throughput is bounded by polling, which is fine at personal scale. Rate limiting is in-process (per API instance); scaling `api` horizontally would need a shared store such as Redis.
