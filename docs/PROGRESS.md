# JobPilot AI — Progress & Milestone Tracking

This document tracks progress against the milestones defined in `jobpilot-ai-advanced-prompt.md`.

---

## Milestone Checklist

- [ ] **M0: Repository Scaffold, Compose, CI, ADR-001, Threat Model Draft**
  - [x] Workspace initialized (Git, .gitignore)
  - [ ] Monorepo layout created (`apps/api`, `apps/web`, `packages/contracts`, `docs/`, `evals/`, `infra/`)
  - [ ] Docker Compose setup (`api`, `web`, `postgres` with pgvector, `redis`)
  - [ ] Environment config templates (`.env.example`)
  - [ ] Root Makefile & tooling configuration (`ruff`, `mypy`, `pytest`, `npm` scripts)
  - [ ] CI workflow definition (GitHub Actions)
  - [ ] ADR-001: Architectural Foundation and Stack Selection
  - [ ] `docs/threat-model.md` draft (STRIDE per component)
  - [ ] Exit Gate Verification: Lint/tests green & container configurations verified

- [ ] **M1: Database Schema + Migrations, Auth, Profile, Onboarding, Authz Sweep**
  - [ ] SQLAlchemy 2.x async models for all core entities (UUIDv7, soft delete where needed, audit constraints)
  - [ ] Alembic migration environment and initial migration
  - [ ] Argon2id password hashing + HttpOnly cookies + CSRF protection
  - [ ] User onboarding and profile data models
  - [ ] Automated cross-user authorization sweep tests (assert 403/404 on cross-tenant access)
  - [ ] Exit Gate Verification: Migrations up/down clean; auth & isolation tests pass

- [ ] **M2: Design System + Shell + Dashboard Skeletons**
  - [ ] React + Vite + TypeScript (strict) setup with Tailwind CSS
  - [ ] Accessible UI component foundation (shadcn-style tokens, dark/light theme, WCAG 2.2 AA)
  - [ ] App Shell: Navigation, header, user profile switch, status indicators
  - [ ] Dashboard skeletons, loading states, empty states, error boundaries
  - [ ] Exit Gate Verification: Component gallery/smoke tests; a11y checks pass

- [ ] **M3: Resume Upload/Parse/Confirm + ProfileFacts**
  - [ ] Resume upload endpoint with magic-byte/MIME validation and size caps
  - [ ] Resume parser (extracting education, experience, skills, projects)
  - [ ] ProfileFact decomposition and verification lifecycle (`candidate` → `confirmed`)
  - [ ] Frontend Resume Studio view for reviewing and confirming atomic facts
  - [ ] Exit Gate Verification: Fixture resumes parse; unconfirmed facts unusable downstream

- [ ] **M4: Job Import, Source Adapters, Dedup, Freshness**
  - [ ] JobSourceAdapter protocol and Compliance Registry (`docs/sources.md`)
  - [ ] Permitted source adapters (Greenhouse/Lever public board, URL/Paste, CSV/JSON, .eml)
  - [ ] SSRF defense and HTML sanitizer for URL imports
  - [ ] Dedup pipeline: Normalized hash fingerprint + trigram similarity flags
  - [ ] Freshness checking and dead-letter queue
  - [ ] Exit Gate Verification: Dedup & SSRF tests pass; idempotent re-import proven

- [ ] **M5: Matching Engine + Explanations + Eval Harness**
  - [ ] Two-stage matching: Deterministic hard filters + weighted scoring (0–100)
  - [ ] Separate confidence metric and unknown handling
  - [ ] Structured explanation payload (`fit_reasons`, `matched_skills`, `missing_or_uncertain`, etc.)
  - [ ] Eval dataset (>=50 labeled synthetic pairs) and metrics runner (precision@k, NDCG)
  - [ ] Exit Gate Verification: Eval metrics pass; unknown-handling tests pass

- [ ] **M6: Resume Studio + Cover Letters + Grounding Validator + Export**
  - [ ] Grounding validator (deterministic entity & quantifier check against confirmed `fact_id`s)
  - [ ] LLM tailored resume & cover letter generation citing `fact_id`s
  - [ ] Diff view with provenance annotations
  - [ ] PDF and DOCX clean export generation
  - [ ] Exit Gate Verification: Hallucination fixtures blocked; export files validate

- [ ] **M7: Application Workflow + Approvals + Tracker + Reminders**
  - [ ] Orchestrator state machine for applications with strict transition guards
  - [ ] ApprovalRecord cryptographic payload hashing (invalidates on change)
  - [ ] Human confirmation requirement for final submission state
  - [ ] Tracker views: Kanban + Table with keyboard accessibility and undo toasts
  - [ ] Activity audit logs and reminder scheduler
  - [ ] Exit Gate Verification: Cannot reach submitted without confirmation; duplicate-apply blocked

- [ ] **M8: Email Triage, Interview Prep, Scam Signals, Analytics**
  - [ ] Uploaded .eml triage classifier generating suggested tracker updates
  - [ ] Interview prep question bank and STAR-format answer scaffolds from verified facts
  - [ ] Probabilistic scam/quality signal engine with transparent evidence
  - [ ] SQL-backed analytics with Wilson confidence intervals, sample sizes, and disclaimers
  - [ ] Exit Gate Verification: Analytics match SQL ground truth on seeded data

- [ ] **M9: Hardening, E2E, Docs, Demo Seed, Final Audit**
  - [ ] Demo seed script with clearly labeled `DEMO` data (profile + 30 jobs)
  - [ ] Comprehensive E2E tests covering full user journey
  - [ ] Final documentation suite (`architecture.md`, `threat-model.md`, `api.md`, `sources.md`, `STATUS.md`)
  - [ ] Security scan and clean quickstart verification
  - [ ] Exit Gate Verification: Full CI green; fresh-clone quickstart runnable in < 15 min

---

## Assumptions & Decisions Log
*See `docs/adr/` for complete Architecture Decision Records.*
- **ADR-001**: Initial Monorepo Structure & Core Stack Choice.
