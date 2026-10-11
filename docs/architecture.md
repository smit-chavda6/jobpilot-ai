# JobPilot AI — Architecture Documentation

## 1. System Overview
JobPilot AI is a compliance-first, human-in-the-loop AI job search assistant. It provides automated resume ingestion, atomic fact verification, job matching with explainable breakdown, grounded tailoring of application materials, and a state-machine guarded application tracker.

```
       +-----------------------------------------------------------+
       |               React + TypeScript Web Client               |
       |  (Tailwind CSS, TanStack Query, React Hook Form, Zod)     |
       +-----------------------------+-----------------------------+
                                     | HTTP / JSON / SSE
                                     v
       +-----------------------------------------------------------+
       |                     FastAPI Backend                       |
       |                                                           |
       |  [Routers (Thin API Handlers)]                            |
       |         |                                                 |
       |  [Services (Business Logic & Grounding Validation)]       |
       |         +-------------------+--------------------+        |
       |         |                   |                    |        |
       |  [Repositories]     [Agents / Orchestrator] [Adapters]    |
       +---------+-------------------+--------------------+--------+
                 |                   |
                 v                   v
      +--------------------+   +-----------------------+
      | PostgreSQL 16      |   | Abstract LLM Provider |
      | + pgvector (HNSW)  |   | (Gemini / OpenAI /    |
      | Redis (Cache/Queue)|   |  MockProvider)        |
      +--------------------+   +-----------------------+
```

## 2. Core Subsystems

### 2.1 Backend Layering
- **Routers**: Thin FastAPI routers handling HTTP status codes, request serialization, dependency injection (`current_user`, database session), and error envelopes.
- **Services**: Pure business logic (e.g., `MatchingService`, `GroundingValidator`, `ApplicationWorkflowService`). Enforce invariants, audit logs, and transaction boundaries.
- **Repositories**: Isolated SQLAlchemy 2.x async queries. **All user queries strictly filtered by `user_id`**.
- **Agents**: Structured agents (Discovery, Resume Parser, Matching, Tailoring, Email Triage, Interview Prep). Communicates strictly with services and abstract `LLMProvider`.
- **Adapters**: Pluggable `JobSourceAdapter` implementations conforming to compliance registry policies.

### 2.2 Error Envelope Standard
All API errors return standard envelopes:
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found or access is denied.",
    "details": {},
    "request_id": "req_01928374-..."
  }
}
```

### 2.3 Authentication & Authorization
- Argon2id password hashing.
- Short-lived JWT access tokens and rotating refresh tokens in `HttpOnly; Secure; SameSite` cookies.
- CSRF double-submit protection on mutating endpoints.
- User-scoped queries prevent cross-tenant access.

### 2.4 Grounding & Truthfulness Guarantee
- User profiles are broken down into atomic **ProfileFacts**.
- Unconfirmed facts cannot be used in generation or matching.
- Any generated resume bullet or cover letter paragraph MUST cite supporting `fact_id`s.
- Deterministic validator verifies entity subsets before export is permitted.
