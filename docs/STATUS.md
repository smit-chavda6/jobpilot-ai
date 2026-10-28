# Status report

Build of 2026-10-28. Every result below was produced on this build; commands and output excerpts
are included. "Not live-verified" means the code path exists and is tested with mocks, but it has
never run against the real third-party service.

## Definition of Done (§19) — checked end to end

The Playwright journey (`apps/web/e2e/journey.spec.ts`) drives the real UI and API through:
register → onboarding (consent, profile, preferences) → upload resume → confirm facts → import a job
(paste) → scored, explained match → tailor (grounded resume + cover letter) → edit in Resume Studio,
save, re-check, export PDF → mark ready → pre-flight → approve (payload hash) → hand-off → explicit
confirmation → tracker shows it in *Applied* → analytics show 1 submitted with "Insufficient data" rates.
It passes against both a fresh local stack (SQLite, inline tasks) and the Docker Compose stack
(Postgres 16, separate worker, nginx).

## Implemented

**P0**
- Auth: Argon2id, email verification and password reset (single-use, hashed, expiring tokens; dev mailbox instead of SMTP), HttpOnly cookie sessions with rotating refresh tokens and reuse detection, CSRF double-submit, throttling with exponential lockout, re-auth for sensitive actions.
- Onboarding wizard (resumable via `onboarding_step`): consent → about you → preferences → resume → confirm facts.
- Resume upload (PDF/DOCX/TXT) with hardened validation; parsing into **candidate** ProfileFacts; only **confirmed** facts are used downstream (tested).
- Job import: paste, URL (SSRF-guarded, robots.txt), CSV/JSON, `.eml`/`.mbox` alert emails, RSS, and the Greenhouse/Lever/Ashby public board APIs. Fingerprint dedup (`UNIQUE(user_id, job_fingerprint)`) plus a trigram "potential duplicate" flag; idempotent re-import; failed-import list; freshness/re-verification.
- Matching: hard filters, then a weighted 0–100 score with separate confidence; unknown ≠ match; explanation object; config snapshot per match; re-score.
- Resume Studio and cover letters: every claim cites fact ids; deterministic grounding validator; keyword classification (supported / adjacent / unsupported); editor with re-check; diff with per-line provenance; PDF and DOCX export, blocked while anything fails grounding.
- Application workflow: state machine with gated transitions, pre-flight checks, screening-question classification (sensitive questions never auto-answered), approval bound to a payload hash (invalidated on change), manual hand-off, explicit submission confirmation, append-only history, duplicate-apply blocked.
- Tracker: Kanban (drag and drop plus a keyboard/screen-reader "Move to…" menu), table view, undo toast, notes with `If-Match`, reminders.
- Analytics computed from stored records: funnel with drop-off, response/interview/offer rates with Wilson 95% CIs and an `n < 20` "insufficient data" threshold, time-to-response distribution, by source, score band vs interview rate, weekly submissions, non-causality note, DEMO data excluded unless opted in.
- Docker Compose (postgres, api, worker, web), `.env.example` with every variable documented, Makefile, README, demo seed script.

**P1 (partly)**
- Interview prep: question bank by type, STAR scaffolds built only from confirmed facts, mock interview sessions with rubric scoring (relevance, structure, specificity, clarity) and a progress chart.
- Scam/quality signals: rule engine with severity, evidence, probabilistic language and a "report false positive" action.
- Email triage of uploaded emails: classification with evidence, suggested tracker updates that need acceptance, draft replies (copy only, never sent).
- In-app notifications and reminders (via the worker); PDF/DOCX export.

**Platform**
- Error envelope, request ids, PII-redacting JSON logs, `/healthz` and `/readyz`, security headers, cursor pagination, ETags, Idempotency-Key, transactional outbox, per-adapter feature flags (env and per user), per-user and global AI token budgets with graceful degradation, AI usage log, versioned prompt files, output filter, circuit breaker.
- Privacy: consent records, full export (JSON + files, ZIP), verified hard deletion with a report, retention purge of AI usage logs and processed outbox events.

## Partially implemented

| Item | What exists | What's missing |
|---|---|---|
| OpenAI / Gemini providers | Implemented against the public APIs, behind the same validation, repair and fallback path as Mock | **Not live-verified** (no API keys used) |
| Greenhouse / Lever / Ashby / RSS | Implemented; tested with mocked HTTP responses | **Not live-verified** against the real services |
| Upload sandboxing | Size/type/magic/macro/zip-bomb/PDF-active-content checks; parsing in a thread with a timeout | No OS-level sandbox process, no ClamAV |
| Rate limiting | Per IP, per user, per expensive endpoint | In-memory per process (see ADR-0003) |
| Frontend API types | OpenAPI exported; request types generated | Response types hand-written (ADR-0007) |
| Semantic matching | 10% semantic component from stored embeddings | JSON vectors with Python cosine, no pgvector/HNSW (ADR-0004) |
| Accessibility | Labels, focus-visible, modal focus trap, skip link, keyboard Kanban alternative, live regions, reduced motion, AA-contrast tokens in both themes | No automated axe audit in CI |

## Not implemented (with reasons)

| Item | Tier | Reason |
|---|---|---|
| Gmail / Outlook OAuth ingestion | P1 | Needs OAuth client registration and credentials; `.eml`/`.mbox` upload covers the flow. The UI lists them as unavailable. |
| pgvector + HNSW; semantic search | P1 | Deferred (ADR-0004) |
| Postgres Row-Level Security | — | Optional per spec; tenancy enforced in `Repo` (ADR-0002) |
| `assisted_fill` (Playwright form filling) and `api_submit` | P2 / spec | No permitted submission API; assisted fill needs a local agent (ADR-0005) |
| Company career-page adapters, n8n hooks, preference learning, i18n | P2 | Out of time |
| Automated `ENCRYPTION_KEY` re-wrap command | — | Manual procedure documented in the runbook |
| Pre-commit hooks, Storybook | — | CI runs the same lint/type/test gates; there is no component gallery page |
| Redis / Celery | — | Replaced by the DB outbox worker (ADR-0003) |

## Manual setup needed

- Real deployments: set strong `JWT_SECRET` and `ENCRYPTION_KEY`, set `APP_ENV=production` (forces Secure cookies, rejects the dev secret) and serve over HTTPS.
- To use a real AI provider, set `LLM_PROVIDER` plus its API key, then verify it yourself (see "Partially implemented").
- No SMTP is wired: verification and reset emails go to the dev mailbox (`GET /api/auth/dev-mailbox`, disabled in production). Production needs a mail sender before email verification is usable.
- Re-check each source's terms before enabling it for other people (`docs/sources.md`).

## Known risks

- Email delivery is not implemented, so password reset in production has no delivery channel.
- Scam signals are heuristics; false negatives are possible. The UI says so.
- The matching evaluation uses a **synthetic** dataset whose tiers were constructed, so near-perfect scores say little about real-world ranking quality.
- In-memory rate limits and the polling worker suit a single instance (personal scale).
- `npm audit` reports one **moderate** advisory in React Router 6 (fixed only in v7, a breaking upgrade). CI fails on high or critical only. Plan the v7 migration.

## Verification commands and results

All run on Windows 11, Python 3.12, Node 22.16, Docker 29.7.

```text
$ cd apps/api && .venv/Scripts/python -m pytest -q --cov=app            # SQLite
165 passed in 137.88s
TOTAL  4940 stmts  369 missed  93%
  services + agents: 2773 stmts, 174 missed → 93.7%   (target ≥ 85%)
  state_machine 100% · grounding 98% · matching 99% · auth_service 96% · security/* 84–100%

$ TEST_DATABASE_URL=postgresql+asyncpg://…/jp_test pytest -q --ignore=tests/test_migrations.py   # Postgres 16
163 passed in 203.59s          (test_migrations.py is SQLite-specific; Postgres migrations checked below)

$ alembic upgrade head && alembic downgrade base && alembic upgrade head   # on Postgres 16
Running upgrade  -> 0001 · Running downgrade 0001 -> · Running upgrade  -> 0001   (30 tables)

$ ruff check app tests alembic scripts      → All checks passed!
$ ruff format --check app tests alembic scripts → all files already formatted
$ mypy app                                   → Success: no issues found in 57 source files

$ python evals/matching/runner.py            # synthetic, labelled dataset
{"pairs": 60, "precision_at_5": 1.0, "ndcg_at_10": 1.0, "spearman": 0.998}

$ cd apps/web && npm run typecheck           → no errors (tsc strict)
$ npm test                                   → Test Files 3 passed · Tests 10 passed
$ npm run build                              → ✓ built (route-level chunks; largest is recharts at 108 kB gzip)

$ E2E_CHANNEL=chrome npx playwright test     # own API (SQLite, mock AI) + Vite
2 passed — full user journey; unauthenticated redirect

$ docker compose up --build -d               # postgres, api, worker, web
api healthy · postgres healthy · web healthy · worker started
GET /api/readyz → {"status":"ready","database":"ok","ai_provider":"mock"}
$ E2E_BASE_URL=http://localhost:8088 E2E_CHANNEL=chrome npx playwright test
2 passed
$ docker compose exec api python -m scripts.seed_demo
Imported 30 DEMO jobs. Created 6 DEMO applications (5 through the full approval + confirmation flow).
```

The CI workflow (`.github/workflows/ci.yml`) runs these gates plus `pip-audit`, `npm audit` and
gitleaks. It has not run on GitHub yet, because nothing has been pushed.

Playwright's bundled Chromium couldn't be downloaded on the build machine, so local E2E runs used the
installed Chrome (`E2E_CHANNEL=chrome`). CI installs the bundled browser.
