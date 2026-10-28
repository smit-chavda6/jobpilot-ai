# Architecture

## Components

```
Browser (React SPA)
   │  same-origin /api  (Vite proxy in dev · nginx in Compose)
   ▼
FastAPI app  ── routers (thin) ─► services (rules) ─► Repo (user-scoped SQL) ─► PostgreSQL 16 / SQLite
   │                │                                     ▲
   │                ├─► agents (typed run(), timeout, retry)
   │                ├─► ai/service (consent, budgets, circuit breaker, schema repair, output filter)
   │                │        └─► LLMProvider: Mock │ OpenAI │ Gemini
   │                └─► adapters (job sources, SSRF-safe fetch)
   │
   └─ outbox_events ─────────► worker (python -m app.worker)
                                 drains outbox · reminders · listing re-verification · retention
```

| Process | Image / command | Notes |
|---|---|---|
| `web` | nginx serving the Vite build | Proxies `/api` to `api:8000`; CSP `script-src 'self'` |
| `api` | `alembic upgrade head && uvicorn app.main:app` | Stateless; uploads on a volume outside the web root |
| `worker` | same image, `python -m app.worker` | All state in the DB, so restarts resume safely |
| `postgres` | `postgres:16-alpine` | Single source of truth |

There is no Redis or Celery: see [ADR-0003](adr/0003-db-outbox-worker-instead-of-redis.md).

## Backend layering

- **Routers** (`app/routers/*`) parse input, call one service or agent, and shape the response. No business rules.
- **Services** (`app/services/*`) hold the rules: ingestion pipeline, matching, grounding, documents, applications, triage, analytics, privacy.
- **Repository** (`app/repositories.Repo`) is the only way to read or write user-owned rows. Every query adds `WHERE user_id = :me`, so another user's row reads as **404** and never as 403 (no existence leak). `tests/test_authz_sweep.py` iterates every private route with a second user's ids.
- **Agents** (`app/agents`) are Discovery, ResumeParsing, Matching, ApplicationPreparation, ApplicationTracking, EmailTriage and InterviewPrep. Each has Pydantic input/output models, a timeout and a retry policy, and reaches the DB only through services.
- **State machine** (`app/services/state_machine.py`) is the only place status transitions are defined. `approved`, `handoff_opened`, `awaiting_user_confirmation` and `submitted_confirmed` are *gated*: they can be reached only through their dedicated action (approval, hand-off, user confirmation), never through a generic move.

## Key flows

**Ingestion.** raw → sanitise (nh3 allowlist, plain-text copy) → parse/normalise → extract skills (ontology plus aliases) → fingerprint (normalised company, title and location plus canonical URL) → dedup (`UNIQUE(user_id, job_fingerprint)` plus a trigram "potential duplicate" flag, never auto-merged) → persist → outbox `job.created` → embed and match. Failures land in `failed_imports`, which the UI lists. Every ingest POST honours `Idempotency-Key`.

**Matching.** Hard filters first (employment type, location/remote, salary, sponsorship, experience in hard mode, blocked companies/keywords). Then a weighted 0–100 score: skills 40, experience 20, education 10, preferences 20, semantic 10. Semantic similarity is capped so it can't rescue an ineligible job. Unknown inputs score neutral-to-penalised and lower `confidence`. Each `JobMatch` stores a config snapshot.

**Generation and grounding.** Generated items have the shape `{text, supporting_fact_ids}`. The deterministic validator rejects items that cite nothing, cite unconfirmed facts, introduce entities (tools, numbers, dates, employers, degrees) absent from the cited facts, or use inflation words. An optional LLM checker may only *add* failures. Export is blocked while any item fails.

**Application.** `saved → tailoring → ready_for_review → awaiting_approval → approved → handoff_opened → awaiting_user_confirmation → submitted_confirmed`. Pre-flight checks cover listing liveness, duplicates, a grounded resume and answered sensitive questions. An `ApprovalRecord` stores the SHA-256 of the canonical package (job, document content hashes, screening answers, adapter level). Any later change invalidates it. Opening the employer's form never changes status to submitted. Every transition appends an `ApplicationActivity` row.

## Cross-cutting

- **Config:** `pydantic-settings`. `JWT_SECRET` and `ENCRYPTION_KEY` are required; production rejects the dev secret and forces Secure cookies.
- **Logging:** JSON lines with `request_id`, plus a redaction filter for emails, phone numbers, API keys, bearer tokens and `password=` pairs.
- **Errors:** `{ "error": { "code", "message", "details", "request_id" } }` on every failure.
- **Pagination:** opaque cursors on jobs and applications.
- **Concurrency:** `ETag` / `If-Match` on profile, documents, applications (notes, moves).
- **Idempotency:** `Idempotency-Key` on job import, application create, prepare and document generation. The stored response is replayed with `Idempotent-Replayed: true`.
- **Outbox:** status changes and notifications are written in the same transaction and processed by the worker.
- **Feature flags:** `SOURCE_*_ENABLED` (global) plus per-user source toggles.

## Frontend

Route-level code splitting (`React.lazy`) and TanStack Query for server state. The API client handles
CSRF double-submit, refresh-on-401 (once) and the error envelope. Design tokens live as CSS variables
in `src/index.css`, with light and dark themes. Every async view goes through `QueryView` for
loading, error and empty states, plus an offline banner. The jobs list is virtualised above 100 rows.
The Kanban has a "Move to…" select on every card as the keyboard and screen-reader alternative
to drag and drop.
