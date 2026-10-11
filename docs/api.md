# JobPilot AI — Complete REST API Specification

This document provides a comprehensive inventory of all REST endpoints exposed by JobPilot AI API (`/api/v1`). All endpoints return standard HTTP status codes and consistent error envelopes.

---

## 1. System & Health

### `GET /healthz`
- **Purpose**: Liveness probe.
- **Auth**: Public.
- **Response**: `{"status": "ok", "timestamp": float}`

### `GET /readyz`
- **Purpose**: Readiness probe reporting dependencies and active LLM provider.
- **Auth**: Public. 
- **Response**: `{"status": "ready", "environment": "development", "llm_provider": "mock", "timestamp": float}`

---

## 2. Authentication & Session Management

### `POST /api/v1/auth/register`
- **Purpose**: Create candidate account with Argon2id password hash.
- **Auth**: Public.
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "Elena Rostova"
  }
  ```
- **Response (201 Created)**: Returns access/refresh tokens and sets HttpOnly cookies.

### `POST /api/v1/auth/login`
- **Purpose**: Authenticate user and issue JWT token pair.
- **Auth**: Public.
- **Request Body**: `{"email": "...", "password": "..."}`
- **Response (200 OK)**: `{"access_token": "...", "token_type": "bearer", "csrf_token": "..."}`

### `POST /api/v1/auth/logout`
- **Purpose**: Invalidate current session and clear HttpOnly cookies.
- **Auth**: Authenticated.

### `GET /api/v1/auth/me`
- **Purpose**: Retrieve current authenticated user details and profile.
- **Auth**: Authenticated (Bearer or Cookie).

---

## 3. Profile & Atomic Facts (Truth over Polish)

### `GET /api/v1/profile`
- **Purpose**: Fetch candidate profile details.
- **Auth**: Authenticated.

### `PUT /api/v1/profile`
- **Purpose**: Update candidate headline, target roles, location preferences, and target salary.
- **Auth**: Authenticated.

### `GET /api/v1/facts`
- **Purpose**: List candidate's atomic ProfileFacts with optional status filter.
- **Query Params**: `confirmation_status` (`candidate` or `confirmed`).
- **Auth**: Authenticated.

### `POST /api/v1/facts`
- **Purpose**: Create a new atomic profile fact directly.
- **Request Body**:
  ```json
  {
    "text": "Architected distributed caching layer serving 10k RPS.",
    "category": "experience",
    "confirmation_status": "confirmed",
    "entities": {"metrics": ["10k RPS"]}
  }
  ```

### `POST /api/v1/facts/{fact_id}/confirm`
- **Purpose**: Human confirmation gate: moves fact from `candidate` to `confirmed`, making it usable downstream.
- **Auth**: Authenticated.

### `DELETE /api/v1/facts/{fact_id}`
- **Purpose**: Delete fact (strictly tenant-isolated).

---

## 4. Resumes & Grounded Studio

### `POST /api/v1/resumes/upload`
- **Purpose**: Hardened resume upload (magic byte verification, 10MB ceiling, text parsing). Decomposes parsed claims into `candidate` ProfileFacts.
- **Request**: Multipart `file`.
- **Response (201 Created)**: Parsed metadata, extracted skills count, candidate facts count.

### `GET /api/v1/resumes`
- **Purpose**: List candidate resumes.

### `POST /api/v1/resumes/{resume_id}/tailor`
- **Purpose**: Generate tailored resume for a target job with structured diff view and fact grounding validation.
- **Request Body**: `{"target_job_id": "...", "version_name": "Optional label"}`
- **Response (201 Created)**: Tailored content, diff view (summary changes, skill reordering, bullet adjustments), cited fact IDs, grounding score.

### `POST /api/v1/resumes/cover-letter`
- **Purpose**: Generate 3-paragraph structured cover letter (Hook, Evidence from confirmed facts, Why company / Close) citing verified `fact_id`s.
- **Request Body**: `{"target_job_id": "..."}`

### `POST /api/v1/resumes/validate-grounding`
- **Purpose**: Standalone deterministic grounding validator. Flags invented metrics, unlisted employers, unlisted degrees, and unsupported technologies.
- **Request Body**: `{"claims": [{"text": "...", "cited_fact_ids": ["..."]}]}`
- **Response**: `{"is_grounded": bool, "grounding_score": float, "violations": []}`

### `GET /api/v1/resumes/versions/{version_id}/export/pdf`
- **Purpose**: Stream clean ATS-compliant single-column PDF resume (ReportLab).
- **Headers**: `Content-Disposition: attachment; filename="resume_{id}.pdf"`

### `GET /api/v1/resumes/versions/{version_id}/export/docx`
- **Purpose**: Stream clean ATS-compliant single-column DOCX resume (python-docx).

---

## 5. Job Ingestion & Matching

### `GET /api/v1/jobs`
- **Purpose**: List ingested jobs with optional search and pagination.
- **Query Params**: `limit`, `offset`, `search`.

### `GET /api/v1/jobs/{job_id}`
- **Purpose**: Get job details and source compliance attribution.

### `POST /api/v1/jobs/import/file`
- **Purpose**: Ingest job listings from uploaded CSV, JSON, or `.eml` MIME alert. Uses SHA-256 fingerprinting for idempotent deduplication.

### `POST /api/v1/jobs/import/url`
- **Purpose**: SSRF-protected job ingestion from permitted direct URL. Validates DNS against RFC 1918, loopback, and cloud metadata IPs before fetching.

### `POST /api/v1/jobs/import/greenhouse`
- **Purpose**: Fetch live public candidate board listings via Greenhouse ATS API.

### `POST /api/v1/jobs/{job_id}/match`
- **Purpose**: Two-stage explainable match engine (Hard filters -> 0-100 weighted scoring) with unknown handling and confirmed fact citations.
- **Response**: `{"score": float, "confidence": float, "hard_filter_passed": bool, "explanation": {...}}`

---

## 6. Applications & Human-in-the-Loop Workflow

### `POST /api/v1/applications`
- **Purpose**: Create tracked job application in `saved` state. Strictly blocks duplicate applications to the same job (409 Conflict).
- **Request Body**: `{"job_id": "...", "notes": "..."}`

### `GET /api/v1/applications`
- **Purpose**: List tracked applications with optional `?status=` filter.

### `GET /api/v1/applications/{app_id}`
- **Purpose**: Full application details, materials payload, cryptographic approval status, and append-only activity audit trail.

### `PATCH /api/v1/applications/{app_id}`
- **Purpose**: Update materials (resume version, cover letter, notes). **Critical invariant**: modifying payload immediately invalidates any active approval and reverts status to `ready_for_review`.

### `POST /api/v1/applications/{app_id}/approve`
- **Purpose**: Human approval gate: user confirms submission package. Computes SHA-256 payload hash and records immutable `ApprovalRecord`. Status advances to `approved`.
- **Request Body**: `{"confirmed_by_user": true}`

### `POST /api/v1/applications/{app_id}/transition`
- **Purpose**: Safe state transition through orchestrator state machine.
- **States**: `saved` -> `preparing` -> `ready_for_review` -> `approved` -> `submitting` -> `submitted_confirmed` -> `interviewing` -> `offer` / `rejected` / `withdrawn`.
- **Request Body**: `{"target_status": "submitted_confirmed", "confirmed_by_user": true, "notes": "..."}`

### `GET /api/v1/applications/reminders`
- **Purpose**: Surfaces automated follow-up reminders for submitted applications (e.g. 7 days post-submission).

---

## 7. Email Triage, Scam Signals & Statistical Analytics

### `POST /api/v1/triage/email`
- **Purpose**: Upload `.eml` email for intent classification (`interview_invite`, `rejection`, `offer`, `assessment_request`, `status_update`, `marketing_or_other`). Returns suggested tracker update with confidence. Zero automated replies.

### `POST /api/v1/jobs/{job_id}/scam-check`
- **Purpose**: Probabilistic scam & predatory signals audit (payment requests, chat apps, freemail domains, outlier salary). Returns transparent evidence list without silent blocking.

### `GET /api/v1/interview-prep/{job_id}`
- **Purpose**: Generate STAR-format answer scaffolds strictly citing confirmed candidate facts, plus reverse questions for interviewer.

### `GET /api/v1/analytics/funnel`
- **Purpose**: SQL-backed application conversion funnel and Wilson score confidence intervals for honest statistical reporting on small candidate sample sizes.
