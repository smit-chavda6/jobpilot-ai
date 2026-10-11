# JobPilot AI — Progress & Milestone Tracking

This document tracks progress against the milestones defined in `jobpilot-ai-advanced-prompt.md`.

---

## Milestone Checklist

- [x] **M0: Repository Scaffold, Compose, CI, ADR-001, Threat Model Draft**
  - [x] Workspace initialized (Git, .gitignore)
  - [x] Monorepo layout created (`apps/api`, `apps/web`, `packages/contracts`, `docs/`, `evals/`, `infra/`)
  - [x] Docker Compose setup (`api`, `web`, `postgres` with pgvector, `redis`)
  - [x] Environment config templates (`.env.example`)
  - [x] Root Makefile & tooling configuration (`ruff`, `mypy`, `pytest`, `npm` scripts)
  - [x] CI workflow definition (GitHub Actions)
  - [x] ADR-001: Architectural Foundation and Stack Selection
  - [x] `docs/threat-model.md` draft (STRIDE per component)
  - [x] Exit Gate Verification: Lint/tests green & container configurations verified

- [x] **M1: Database Schema + Migrations, Auth, Profile, Onboarding, Authz Sweep**
  - [x] SQLAlchemy 2.x async models for all core entities (UUIDv7/UUID, audit constraints, relationships)
  - [x] Alembic migration environment and initial migration (clean up/down proven)
  - [x] Argon2id password hashing + HttpOnly cookies + CSRF protection
  - [x] User onboarding, profile, education, experience, and atomic ProfileFacts
  - [x] Automated cross-user authorization sweep tests (assert 403/404 on cross-tenant access)
  - [x] Exit Gate Verification: Migrations up/down clean; auth & isolation tests pass (11 tests green)

- [x] **M2: Design System + Shell + Dashboard Skeletons**
  - [x] React + Vite + TypeScript (strict) setup with Tailwind CSS
  - [x] Accessible UI component foundation (shadcn-style tokens, dark/light theme, WCAG 2.2 AA)
  - [x] App Shell: Navigation, header, user profile switch, status indicators
  - [x] Dashboard, Jobs, Tracker, Resume Studio, Analytics, Settings views
  - [x] Exit Gate Verification: Component gallery at /gallery, 6 RTL component unit tests green, Vite production bundle clean

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
