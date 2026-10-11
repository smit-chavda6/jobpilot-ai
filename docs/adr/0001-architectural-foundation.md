# ADR-001: Architectural Foundation and Technology Stack

## Status
Accepted

## Context
JobPilot AI requires a robust, compliance-first, human-in-the-loop architecture designed to assist candidates with high fidelity, ground truth enforcement, and auditability. The system processes resumes, job postings, semantic embeddings, and application lifecycle states while strictly preventing unapproved external actions or hallucinations.

## Decisions

1. **Backend Language & Framework**:
   - Python 3.12+ with FastAPI.
   - Pydantic v2 for data contracts and validation.
   - SQLAlchemy 2.x async ORM with PostgreSQL 16.
   - Alembic for strict migration control.
   - Layered architecture: `router (thin) -> service (business rules) -> repository (data access)`.
   - Explicit agent isolation: Agents interact with business services, never raw database sessions directly.

2. **Frontend Framework & Styling**:
   - React 18+ with TypeScript (strict mode enabled).
   - Vite for build tooling.
   - Tailwind CSS for design system tokenization.
   - TanStack Query (React Query) for server-state caching, React Router for navigation, React Hook Form + Zod for client-side contract validation.

3. **Storage & Vectors**:
   - PostgreSQL 16 with `pgvector` extension for semantic embedding storage and HNSW index retrieval.
   - Redis for caching, rate limiting, and background queue broker.

4. **AI & Grounding Isolation**:
   - Server-side only AI calls through an abstract `LLMProvider` interface.
   - Implementations for Gemini, OpenAI, and a deterministic `MockProvider` for test isolation.
   - Grounding Validator enforces that generated claims cite verified atomic `ProfileFact` IDs.

5. **Security & Human-in-the-loop**:
   - User approval records hashed with payload content.
   - Automated checks against cross-tenant data leaks (all queries scoped by `user_id`).
   - Strict SSRF protections on job URL imports.

## Consequences
- Clean separation of concerns with verifiable type contracts.
- Rapid local execution using Docker Compose or local Python/Node runners.
- Zero client-side AI key exposure.
- Fully reproducible test runs without live third-party API dependencies.
