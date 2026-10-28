# ADR-0001: Architectural foundation

- **Status:** accepted · 2026-10-28

## Context
The spec (§3) asks for a React SPA, a FastAPI backend layered router → service → repository,
agents, adapters, Postgres, a worker and Docker Compose.

## Decision
- Monorepo: `apps/api` (FastAPI, SQLAlchemy 2 async, Alembic), `apps/web` (Vite + React + TS strict), `infra`, `docs`, `evals`, `packages/contracts`.
- Same-origin deployment: nginx serves the SPA and proxies `/api` (Vite proxies in dev). Cookies are first-party; the SPA doesn't depend on CORS.
- All user-owned data access goes through one `Repo` class that injects `user_id`, so tenancy is enforced in one place.
- Agents live in one module (`app/agents/__init__.py`) rather than one package each: they are thin typed wrappers over services, and one module keeps the shared timeout/retry base in view.
- One Alembic baseline migration (`0001`). Later schema changes get new revisions.
- SQLite (aiosqlite) for local development and the default test run; PostgreSQL 16 in Compose and CI. The same suite runs on both (`TEST_DATABASE_URL`).

## Consequences
Easy to run locally without Docker. Postgres-only features (RLS, pgvector, trigram indexes) are avoided or emulated so behaviour matches on both; see ADR-0002 and ADR-0004.
