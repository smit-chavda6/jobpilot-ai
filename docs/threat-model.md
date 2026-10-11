# JobPilot AI — Threat Model (STRIDE)

This document formalizes the threat model for JobPilot AI based on STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) across all primary components and input vectors.

---

## 1. System Overview & Trust Boundaries

Trust boundaries exist between:
1. **Public Internet & Ingestion Services**: External job URLs, user file uploads, external webhook/email payloads.
2. **Browser & Application API**: Web client communicating with FastAPI over HTTPS.
3. **Application API & AI Providers**: Outbound calls to Google Gemini / OpenAI APIs.
4. **Application API & Internal Datastores**: PostgreSQL (pgvector) and Redis.
5. **Tenant Isolation Boundary**: Independent user contexts within the shared multi-tenant database.

---

## 2. Component Analysis (STRIDE)

| Component | Threat Category | Threat Description | Mitigations & Controls |
|---|---|---|---|
| **Job URL Ingestion** | Tampering / DoS | SSRF attack via crafted job URL pointing to cloud metadata (`169.254.169.254`), localhost, or private subnets. | DNS resolution validation blocking loopback, link-local, private RFC 1918 ranges before request; redirect inspection; strict timeout & response size limits. |
| **Resume & File Uploads** | Tampering / EoP | Malicious executable upload, ZIP bomb, macro-laden DOCX, or exploit payloads inside PDF files. | Strict MIME + magic-byte verification (not trusting client extension); 10MB size ceiling; sandboxed text-extraction parsing; random storage filenames outside web root. |
| **AI Prompting & LLM Calls** | Tampering / Info Disclosure | Prompt injection embedded in job descriptions or resume inputs attempting to override instructions or exfiltrate system data. | Strictly treat untrusted inputs as isolated data blocks with XML/markdown boundaries; code-level enforcement prevents LLMs from directly executing side effects; output schema validation via Pydantic; response secret scanner. |
| **Authentication & Sessions** | Spoofing / Tampering | Session hijacking, credential stuffing, CSRF attacks on mutation endpoints. | Argon2id password hashing with salt; HttpOnly, Secure, SameSite cookies for short-lived JWTs and rotating refresh tokens; double-submit CSRF tokens for state-changing requests; login backoff. |
| **Tenant Access / Data Layer** | Info Disclosure / Tampering | IDOR (Insecure Direct Object Reference) accessing another candidate's resumes, jobs, or tracker activities. | Mandatory user-scoped queries across all repositories (`WHERE user_id = :current_user_id`); automated cross-tenant security test sweep asserting 403/404. |
| **Application Submission Gate** | Tampering / Repudiation | Automated submission without explicit human verification; altered application payload after approval. | State machine blocks `submitted_confirmed` without recorded user confirmation action; `ApprovalRecord` cryptographically hashes the reviewed payload; any modification invalidates the approval token. |
| **AI Resource Utilization** | Denial of Service | Cost-exhaustion attacks triggering repetitive LLM calls. | Per-user rate limiting, global and per-user token budgets with automatic graceful fallback to deterministic heuristic matching and parsing. |
| **Third-Party Integrations** | Info Disclosure | Token leakage of connected OAuth credentials (Gmail / ATS). | AES-256-GCM / Fernet field-level encryption at rest; read-only OAuth scopes strictly enforced; re-authentication required before changing integrations. |

---

## 3. Residual Risk & Review Cadence
- **LLM Non-Determinism**: Grounding Validator provides deterministic entity verification on top of LLM outputs.
- **Third-Party Scraping Restrictions**: Documented in `docs/sources.md` (Compliance Registry); disallowed domains default to manual guided flow.
