# JobPilot AI

A compliance-first, human-in-the-loop job-search assistant. It imports jobs from sources whose terms
allow it, scores them against a profile you have verified fact by fact, drafts tailored resumes and
cover letters in which every claim cites one of your confirmed facts, and walks you through an
application you approve and submit yourself. It never mass-applies, scrapes sites that forbid it,
sends email, or presses a submit button for you.

| | |
|---|---|
| **Frontend** | React 18 + TypeScript (strict), Vite, Tailwind, TanStack Query/Virtual, React Hook Form + Zod, Recharts |
| **Backend** | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 (SQLite for local dev/tests) |
| **Worker** | `python -m app.worker`: transactional-outbox consumer, reminders, listing re-verification, retention |
| **AI** | Provider-agnostic `LLMProvider` (Mock, OpenAI, Gemini). Mock is deterministic and the default. |

Status, verified results and known gaps are in [docs/STATUS.md](docs/STATUS.md).

---

## Quickstart (Docker, about 5 minutes)

Needs Docker Desktop (or Docker Engine with Compose v2).

```bash
cp .env.example .env          # defaults work for local use; change JWT_SECRET/ENCRYPTION_KEY for anything shared
docker compose up --build -d  # postgres, api (runs migrations), worker, web
```

Open **http://localhost:8080**, create an account and follow the onboarding wizard.

Optional DEMO data (sample profile, 30 demo jobs, 6 demo applications, all labelled DEMO):

```bash
docker compose exec api python -m scripts.seed_demo   # then sign in as demo@example.com / DemoPassw0rd!
```

Stop with `docker compose down` (add `-v` to delete the database and uploads).
If port 8080 is taken, set `WEB_PORT=8088` in `.env`.

## Local development (without Docker)

Needs Python 3.12 and Node 22.

```bash
cp .env.example .env

# API (http://localhost:8000, docs at /api/docs). Uses SQLite at apps/api/var/jobpilot.db.
cd apps/api
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # macOS/Linux: .venv/bin/python
mkdir -p var && .venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Web (http://localhost:5173), in a second terminal. Vite proxies /api to :8000.
cd apps/web
npm ci
npm run dev
```

With `make` available, the same steps are `make setup`, `make api` and `make web`.
Run `make help` to list every target.

## Tests and quality gates

| What | Command | Notes |
|---|---|---|
| Backend tests + coverage | `cd apps/api && .venv/Scripts/python -m pytest --cov=app` | SQLite per test |
| Backend tests on Postgres | `make test-pg` | throwaway `postgres:16` container; or set `TEST_DATABASE_URL` |
| Lint / types (API) | `ruff check app tests alembic scripts` · `mypy app` | strict mypy on state machine, grounding, matching, fingerprint, security |
| Frontend tests | `cd apps/web && npm test` | Vitest + React Testing Library |
| Frontend types / build | `npm run typecheck` · `npm run build` | |
| End-to-end journey | `cd apps/web && npx playwright test` | starts its own API (fresh SQLite, mock AI) and Vite server |
| E2E against the Docker stack | `E2E_BASE_URL=http://localhost:8080 npx playwright test` | Postgres + separate worker |
| Matching evaluation | `make eval` | fails on regression beyond tolerance |

If Playwright can't download its browser, run with an installed one: `E2E_CHANNEL=chrome npx playwright test`.
No test calls a real AI API, sends email or submits an application.

## Configuring AI providers

Set `LLM_PROVIDER` in `.env`:

| Value | Needs | Behaviour |
|---|---|---|
| `mock` (default) | nothing | Deterministic, local. Nothing leaves the server. Generation uses rule-based drafting. |
| `openai` | `OPENAI_API_KEY` (+ optional `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`) | Structured outputs validated against Pydantic schemas; one bounded repair attempt, then fallback. |
| `gemini` | `GEMINI_API_KEY` (+ optional `GEMINI_MODEL`) | Same contract as OpenAI. |

The API refuses to start if the chosen provider has no key. Every call checks the user's consent and
the per-user and global daily token budgets (`AI_DAILY_TOKEN_BUDGET_PER_USER`,
`AI_DAILY_TOKEN_BUDGET_GLOBAL`). A circuit breaker trips on repeated provider failures, and when
any check fails the feature falls back to deterministic logic.

> The OpenAI and Gemini adapters are implemented against their public APIs but have **not been
> live-verified** in this build (no keys were used). Treat them as untested until you run them.

The grounding validator always runs in code, whatever the provider. A generated claim that cites
no confirmed fact, or mentions an employer, tool, number or date that its cited facts don't contain,
is blocked from export.

## Enabling and disabling sources

Job sources are listed in the UI under **Sources & Integrations** and documented in
[docs/sources.md](docs/sources.md) (the compliance registry). Each source can be switched off per
user, and globally with the `SOURCE_*_ENABLED` variables. LinkedIn, Indeed, Glassdoor and Naukri
are **disabled by policy**: their terms forbid automated access, so the UI offers the manual path
instead (paste the description, or upload their alert emails as `.eml`).

## Architecture in one paragraph

The SPA talks to a FastAPI app through same-origin `/api` (Vite proxy in dev, nginx in Compose).
Routers are thin; business rules live in `app/services`; every user-owned query goes through
`app/repositories.Repo`, which always filters by `user_id`. Agents (`app/agents`) wrap services
with typed inputs/outputs, timeouts and retry policies. Application status changes only through
`app/services/state_machine.py`. Approvals are bound to a SHA-256 hash of the exact package shown,
and `submitted_confirmed` is reachable only by the user's explicit confirmation. Side effects that must
not be lost go to an outbox table drained by the worker. See [docs/architecture.md](docs/architecture.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `JWT_SECRET` / `ENCRYPTION_KEY` validation error on start | Both are required; `.env.example` has dev values. Generate real ones with the commands in `.env.example`. |
| "Missing or invalid CSRF token" | The SPA fetches a token from `/api/auth/csrf`. Reload the page; make sure you open the app through the web origin (5173 or 8080), not the API port. |
| Logged out right after signing in over plain HTTP in production | `APP_ENV=production` forces `Secure` cookies; serve over HTTPS. |
| Imported job shows "Scoring in progress" | In Compose, scoring runs in the worker: check `docker compose logs worker`. Locally, `INLINE_TASKS=true` scores immediately. |
| Generated document won't export | At least one item fails grounding. Open it in Resume Studio; the failing items show the reason. |
| Rates show "Insufficient data" | Rates are hidden until `ANALYTICS_MIN_N` (default 20) records exist. |
| Port already in use | Change `WEB_PORT` (Compose) or `--port` (uvicorn / `npm run dev -- --port`). |

## Repository layout

```
apps/api            FastAPI app: app/{routers,services,repositories.py,agents,adapters,ai,security,prompts}
apps/api/alembic    migrations          apps/api/scripts   seed_demo.py
apps/api/tests      pytest suite (+ fixtures)
apps/web            React SPA: src/{pages,components,api,lib,test}, e2e/ (Playwright)
packages/contracts  openapi.json exported from the API (regenerate with `make openapi`)
evals/matching      synthetic labelled dataset, generator, runner, baseline
infra               Dockerfiles, nginx.conf        docs  architecture, ADRs, threat model, sources, API, runbook, status
```

## License and data

Personal project. Demo and evaluation data are synthetic and labelled as such. Job URLs in demo
data use the reserved `example.com` domain.
