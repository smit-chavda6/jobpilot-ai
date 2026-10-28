# Progress

Milestones from the build spec (§17). Evidence for every gate is in [STATUS.md](STATUS.md).

| M | Deliverable | Gate | State |
|---|---|---|---|
| M0 | Scaffold, Compose, CI, ADR-001, threat model | `docker compose up` healthy; CI config | ✅ Compose verified locally; CI not yet run on GitHub |
| M1 | Schema + migrations, auth, profile, onboarding, authz sweep | Migrations up/down clean; auth and isolation tests | ✅ SQLite and Postgres |
| M2 | Design system, shell, dashboard | Component tests; a11y basics | ✅ tokens, light/dark, keyboard paths (no Storybook, no axe in CI) |
| M3 | Resume upload/parse/confirm, ProfileFacts | Fixture resumes parse; unconfirmed facts unusable | ✅ |
| M4 | Job import, dedup, freshness | Dedup and SSRF tests; idempotent re-import | ✅ (public boards not live-verified) |
| M5 | Matching, explanations, eval harness | Eval metrics; unknown-handling tests | ✅ (synthetic eval) |
| M6 | Resume Studio, cover letters, grounding, export | Hallucination fixtures blocked; PDF/DOCX export | ✅ |
| M7 | Application workflow, approvals, tracker, reminders | Submitted requires confirmation; duplicate apply blocked | ✅ |
| M8 | Email triage, interview prep, scam signals, analytics | Analytics match SQL ground truth | ✅ (uploaded email only; no OAuth) |
| M9 | Hardening, E2E, docs, demo seed, audit | Full suite green; quickstart | ✅ locally; CI pending first push |

## Assumptions

- Single-user-per-account, personal scale: in-process rate limits and a polling worker are enough.
- The Mock provider is the default, so the product works fully without any AI key.
- Source terms were reviewed on 2026-10-28 and must be re-checked before wider use.

## Known gaps

See "Partially implemented" and "Not implemented" in STATUS.md.
