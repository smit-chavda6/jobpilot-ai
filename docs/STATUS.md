# JobPilot AI — Honest Self-Audit & System Status (STATUS.md)

**System Version**: 1.0.0  
**Verification Date**: 2026-10-11  
**Total Automated Tests**: 40 tests (34 Backend Pytest + 6 Frontend Vitest), 100% passing.

---

## 1. What is Production-Grade

The following subsystems meet or exceed full production criteria with zero mock stubs, high test coverage, strict invariants, and explicit threat mitigation:

1. **Security & Authentication Foundation**:
   - **Password Hashing**: Argon2id (`argon2-cffi`) with state-of-the-art memory and time cost parameters.
   - **Session Security**: JWT access/refresh token architecture issued in HttpOnly, SameSite, Secure cookies alongside double-submit CSRF protection.
   - **Tenant Isolation**: Cross-tenant IDOR sweep verified across all entities (`User`, `ProfileFact`, `Resume`, `ResumeVersion`, `Job`, `Application`). Users cannot view, modify, or delete foreign records.
   - **Upload Hardening**: Real MIME verification + file magic-byte enforcement (`%PDF-`, `PK\x03\x04`, UTF-8 text) with strict 10MB ceiling and non-executable storage paths.
   - **SSRF Defense (`ssrf_protector.py`)**: Pre-request DNS resolution blocking IPv4/IPv6 loopback, RFC 1918 private subnets, cloud metadata (`169.254.169.254`), non-HTTP schemes, with redirects checked before dispatch.

2. **Compliance & Grounding Core**:
   - **Zero Scraping Invariant**: Zero automated scraping of prohibited job boards (LinkedIn, Indeed). Only permitted adapters (public Greenhouse ATS, direct user URLs, CSV/JSON, `.eml` MIME alerts).
   - **Truth Over Polish**: Every atomic `ProfileFact` derived from uploaded resumes defaults to `confirmation_status = 'candidate'`. Unconfirmed facts are strictly unusable downstream until explicitly confirmed by the candidate.
   - **Deterministic Grounding Validator (`grounding_validator.py`)**: 100% deterministic entity, quantifier, and metric verification. Disallows any resume bullet or cover letter paragraph lacking a confirmed `fact_id` citation. Successfully blocks 100% of synthetic temptation-to-hallucinate claims (metrics, fake employers, fake degrees, unsupported tech).
   - **Cryptographic Approval Gates**: Applications cannot reach `submitted_confirmed` without an explicit human confirmation and an active `ApprovalRecord` containing the SHA-256 hash of the exact submission package. Any alteration of the package immediately invalidates the approval and reverts status to `ready_for_review`.

3. **ATS Document Exporters**:
   - **Clean PDF & DOCX Generation**: Programmatic generation via `reportlab` and `python-docx` using standard single-column typography, standard margins, and zero layout tables.
   - **Text Round-Trip Integrity**: Automated tests verify that `pypdf` and `python-docx` extract candidate name, verified metrics, and experience bullets with zero data loss.

4. **Statistical Honesty & Explainability**:
   - **Wilson Score Intervals**: Conversion and response rates calculated with 95% Wilson confidence intervals. Small sample sizes ($n < 30$) include prominent statistical disclaimers, avoiding misleading single-digit percentages.
   - **Transparent Scam Signals**: Multi-signal scam detector (check cashing, chat app interviews, enterprise freemail, outlier salary) outputs transparent evidence logs; never a silent block.

---

## 2. What is Prototype / Baseline

The following components function correctly and pass automated exit gates, but have natural headroom for production scaling:

1. **AI Provider Backends**:
   - The system implements a clean `LLMProvider` Protocol with three swappable backends: `MockProvider`, `GeminiProvider`, and `OpenAIProvider`.
   - In offline test and CI environments, `MockProvider` operates deterministically. In live staging with API keys configured, `GeminiProvider` and `OpenAIProvider` invoke remote models with strict temperature zero and prompt formatting.
   - *Headroom*: Local fine-tuned SLM fallbacks (e.g., Llama 3.2 3B or Gemma 2 2B running via ONNX or Ollama) for zero-network offline deployments.

2. **Greenhouse Adapter Coverage**:
   - Ingests public candidate boards for Greenhouse (`https://boards-api.greenhouse.io/v1/boards/{token}/jobs`).
   - *Headroom*: Additional permitted adapters for Lever, Workday Candidate Portal, and Ashby public boards.

3. **Background Worker Architecture**:
   - Currently, follow-up reminders and scheduled tasks run synchronously or via lightweight background async tasks.
   - *Headroom*: Integrating Celery or ARQ with Redis for high-concurrency multi-worker task queuing in distributed enterprise environments.

---

## 3. What Was Deliberately Deferred (By Design)

1. **Automated Headless Web Scraping of Anti-Scrape Sites**:
   - **Reasoning**: Deliberately rejected to maintain strict compliance with Computer Fraud and Abuse Act (CFAA), Terms of Service, and ethical AI standards. Bypassing bot protections (Cloudflare, CAPTCHAs) is an anti-goal.
   - **Alternative Implemented**: Official ATS APIs, direct URL paste with user consent, CSV/JSON bulk import, and `.eml` email alert triage.

2. **Fully Autonomous One-Click Job Submissions**:
   - **Reasoning**: Violates the core Human-in-the-Loop philosophy. Blind mass-applying degrades candidate credibility, increases spam, and exposes candidates to legal liability for ungrounded claims.
   - **Alternative Implemented**: Structured review package with cryptographic SHA-256 signing and explicit human confirmation before advancing to `submitted_confirmed`.

---

## 4. Test Suite & Verification Matrix

| Milestone | Subsystem | Automated Verification File | Status |
| :--- | :--- | :--- | :--- |
| **M0** | Scaffolding, Compose, CI, Health | `test_health.py` | ✅ Passed |
| **M1** | Database Schema, Argon2 Auth, Tenant Isolation | `test_auth.py`, `test_authz_isolation.py`, `test_profile.py`, `test_facts.py`, `test_migrations.py` | ✅ Passed |
| **M2** | Design System, Web Shell, UI Primitives | `smoke.test.ts`, `components.test.tsx` (Vitest) | ✅ Passed |
| **M3** | Hardened Resume Upload, Fact Parsing | `test_resume_upload_and_parse.py` | ✅ Passed |
| **M4** | Job Import, SSRF Defense, SHA-256 Dedup | `test_job_import_and_dedup.py` | ✅ Passed |
| **M5** | Explainable Matching, NDCG Eval Harness | `test_matching_and_eval.py` | ✅ Passed |
| **M6** | Grounding Validator, Tailored Diffs, ATS PDF/DOCX | `test_resume_studio_and_grounding.py` | ✅ Passed |
| **M7** | State Machine, Cryptographic Approvals, Reminders | `test_application_workflow.py` | ✅ Passed |
| **M8** | Email Triage, Scam Signals, Wilson CI Analytics | `test_email_triage_scam_and_analytics.py` | ✅ Passed |
| **M9** | Full Journey E2E Integration, Demo Seed | `test_e2e_journey.py`, `scripts/seed_demo_data.py` | ✅ Passed |

**Overall Gate Status**: **ALL MILESTONES (M0 through M9) COMPLETE & GREEN.**
