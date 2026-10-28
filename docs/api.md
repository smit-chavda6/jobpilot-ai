# API reference

The machine-readable contract is **`packages/contracts/openapi.json`** (OpenAPI 3.1, exported from
the running app with `make openapi`). Interactive docs are served at **`/api/docs`**.

## Conventions

| | |
|---|---|
| Auth | Session cookies (`jp_access` 15 min, `jp_refresh` 14 days, rotating). Call `GET /api/auth/csrf` first. |
| CSRF | Every `POST/PUT/PATCH/DELETE` under `/api` must send `X-CSRF-Token` equal to the `jp_csrf` cookie. Otherwise `403 csrf_failed`. |
| Errors | `{"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}`. `X-Request-ID` is echoed on every response. |
| Idempotency | `Idempotency-Key` header on job imports, `POST /api/applications`, `.../prepare` and `POST /api/documents`. A repeat with the same key and body replays the first response (`Idempotent-Replayed: true`); the same key with a different body returns `idempotency_mismatch`. |
| Concurrency | `GET` profile, document and application return `ETag: W/"<version>"`. Send `If-Match` on `PATCH /api/profile`, `PUT /api/documents/{id}`, notes and moves; a stale version returns `412`. |
| Pagination | `GET /api/jobs` and `GET /api/applications` return `{items, next_cursor}`; pass `cursor=` for the next page. |
| Re-auth | Export, account deletion and integration changes need `POST /api/auth/reauth` within the last 5 minutes, or they return `403 reauth_required`. |
| Rate limits | `429 rate_limited` with `details.retry_after_seconds`. |

Error codes in use: `unauthorized`, `session_expired`, `invalid_credentials`, `weak_password`,
`invalid_token`, `csrf_failed`, `reauth_required`, `forbidden`, `not_found`, `precondition_failed`,
`idempotency_mismatch`, `conflict`, `locked`, `duplicate_application`, `invalid_transition`,
`preflight_failed`, `payload_changed`, `approval_invalid`, `confirmation_required`, `resume_required`,
`undo_unavailable`, `grounding_failed`, `no_confirmed_facts`, `invalid_category`, `upload_rejected`,
`invalid_file`, `parse_failed`, `invalid_row`, `fetch_blocked`, `fetch_failed`, `invalid_feed`,
`unknown_source`, `missing_param`, `invalid_source_params`, `source_disabled`, `invalid_cursor`,
`not_pending`, `session_completed`, `bad_request`, `unprocessable`, `rate_limited`.

## Example: the core journey with curl

```bash
B=http://localhost:8080; J=cookies.txt
CSRF=$(curl -s -c $J $B/api/auth/csrf | python -c "import sys,json;print(json.load(sys.stdin)['csrf_token'])")
H=(-b $J -c $J -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json")

curl -s "${H[@]}" $B/api/auth/register -d '{"email":"me@example.com","password":"Sup3rSecurePass"}'
curl -s "${H[@]}" $B/api/consents -d '{"purpose":"ai_processing","granted":true}'
curl -s -b $J -c $J -H "X-CSRF-Token: $CSRF" -F file=@resume.pdf $B/api/resumes          # -> candidate facts
curl -s "${H[@]}" $B/api/facts/status -d '{"fact_ids":["<id>", "..."],"status":"confirmed"}'
curl -s "${H[@]}" -H "Idempotency-Key: imp-1" $B/api/jobs/import/manual_paste -d '{"text":"<job description>"}'
curl -s -b $J $B/api/jobs/<job_id>                                                          # match + explanation
APP=$(curl -s "${H[@]}" $B/api/applications -d '{"job_id":"<job_id>"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s "${H[@]}" -X POST $B/api/applications/$APP/prepare                                  # grounded resume + cover letter
curl -s "${H[@]}" -X POST $B/api/applications/$APP/ready
HASH=$(curl -s "${H[@]}" -X POST $B/api/applications/$APP/request-approval | python -c "import sys,json;print(json.load(sys.stdin)['payload_hash'])")
curl -s "${H[@]}" $B/api/applications/$APP/approve -d "{\"payload_hash\":\"$HASH\"}"
curl -s "${H[@]}" -X POST $B/api/applications/$APP/handoff                                  # returns the employer URL; nothing is submitted
curl -s "${H[@]}" $B/api/applications/$APP/confirm-submission -d '{"confirmed":true}'      # only now: submitted_confirmed
```

### Selected response shapes

`GET /api/jobs/{id}` (abridged):

```json
{
  "id": "…", "title": "Machine Learning Engineer", "company": "Nimbus AI",
  "match": {"score": 88.1, "confidence": 1.0, "eligible": true, "recommended_action": "apply"},
  "match_detail": {
    "breakdown": {"components": {"skills": {"value": 0.93, "status": "known", "weight": 0.4, "contribution": 37.4, "detail": "8/8 required and 1/3 preferred skills verified"}},
                  "filters": [{"name": "location", "passed": true, "reason": "…"}]},
    "explanation": {"fit_reasons": ["…"], "matched_skills": ["Python"], "missing_or_uncertain": ["Related (not identical) skills: Kubernetes"],
                    "projects_to_highlight": ["<fact_id>"], "questions_to_investigate": ["What is the salary range?"], "recommended_action": "apply"},
    "config_snapshot": {"version": "match-config@1", "weights": {"skills": 0.4, "experience": 0.2, "education": 0.1, "preferences": 0.2, "semantic": 0.1}}
  },
  "scam_report": {"level": "none", "confidence": 0, "summary": "No common scam signals detected. This is not a guarantee of legitimacy.", "signals": []}
}
```

Generated document item: `{"id": "…", "section": "experience", "kind": "claim", "text": "…", "supporting_fact_ids": ["<fact_id>"]}`.
Grounding report: `{"passed": true, "checked": 11, "failed": 0, "items": {"<item_id>": {"passed": true, "reasons": []}}, "validator": "deterministic@1"}`.

Analytics rates: `{"n": 22, "successes": 6, "rate": 0.273, "ci_low": 0.13, "ci_high": 0.48, "insufficient_data": false, "min_n": 20}` (Wilson 95% interval).

## Endpoints

### health

| Method | Path |
|---|---|
| GET | `/healthz` |
| GET | `/readyz` |

### auth

| Method | Path |
|---|---|
| GET | `/api/auth/csrf` |
| POST | `/api/auth/register` |
| POST | `/api/auth/login` |
| POST | `/api/auth/refresh` |
| POST | `/api/auth/logout` |
| GET | `/api/auth/me` |
| POST | `/api/auth/verify-email` |
| POST | `/api/auth/request-verification` |
| POST | `/api/auth/forgot-password` |
| POST | `/api/auth/reset-password` |
| POST | `/api/auth/reauth` |
| GET | `/api/auth/dev-mailbox` |

### profile

| Method | Path |
|---|---|
| GET | `/api/profile` |
| PATCH | `/api/profile` |
| GET | `/api/consents` |
| POST | `/api/consents` |
| GET | `/api/resumes` |
| POST | `/api/resumes` |
| DELETE | `/api/resumes/{resume_id}` |
| GET | `/api/facts` |
| POST | `/api/facts` |
| PATCH | `/api/facts/{fact_id}` |
| DELETE | `/api/facts/{fact_id}` |
| POST | `/api/facts/status` |
| GET | `/api/skills` |

### jobs

| Method | Path |
|---|---|
| GET | `/api/jobs` |
| GET | `/api/jobs/failed-imports` |
| POST | `/api/jobs/failed-imports/{item_id}/resolve` |
| GET | `/api/jobs/{job_id}` |
| POST | `/api/jobs/import/file` |
| POST | `/api/jobs/import/email` |
| POST | `/api/jobs/import/{source}` |
| GET | `/api/sources` |
| PUT | `/api/sources/{source_id}` |
| POST | `/api/jobs/bulk` |
| POST | `/api/jobs/{job_id}/reverify` |
| POST | `/api/jobs/{job_id}/scam-feedback` |
| POST | `/api/matches/rescore` |
| GET | `/api/saved-filters` |
| PUT | `/api/saved-filters` |

### documents

| Method | Path |
|---|---|
| GET | `/api/documents` |
| POST | `/api/documents` |
| GET | `/api/documents/{doc_id}` |
| PUT | `/api/documents/{doc_id}` |
| DELETE | `/api/documents/{doc_id}` |
| GET | `/api/documents/{doc_id}/export` |

### applications

| Method | Path |
|---|---|
| GET | `/api/applications` |
| POST | `/api/applications` |
| GET | `/api/applications/{app_id}` |
| PATCH | `/api/applications/{app_id}/notes` |
| POST | `/api/applications/{app_id}/prepare` |
| PUT | `/api/applications/{app_id}/documents` |
| POST | `/api/applications/{app_id}/ready` |
| POST | `/api/applications/{app_id}/request-approval` |
| POST | `/api/applications/{app_id}/approve` |
| POST | `/api/applications/{app_id}/handoff` |
| POST | `/api/applications/{app_id}/confirm-submission` |
| POST | `/api/applications/{app_id}/move` |
| POST | `/api/applications/{app_id}/undo` |
| POST | `/api/applications/{app_id}/screening` |
| PUT | `/api/applications/{app_id}/screening/{answer_id}` |
| POST | `/api/applications/{app_id}/reminders` |
| GET | `/api/reminders` |
| POST | `/api/reminders/{reminder_id}/done` |
| GET | `/api/interviews` |

### insights

| Method | Path |
|---|---|
| POST | `/api/triage/upload` |
| GET | `/api/triage` |
| POST | `/api/triage/{email_id}/accept` |
| POST | `/api/triage/{email_id}/dismiss` |
| POST | `/api/triage/{email_id}/import-jobs` |
| GET | `/api/interview-prep/bank` |
| POST | `/api/interview-prep/star` |
| GET | `/api/interview-prep/sessions` |
| POST | `/api/interview-prep/sessions` |
| GET | `/api/interview-prep/sessions/{session_id}` |
| POST | `/api/interview-prep/sessions/{session_id}/answers` |
| GET | `/api/analytics` |

### account

| Method | Path |
|---|---|
| GET | `/api/settings` |
| PATCH | `/api/settings` |
| POST | `/api/privacy/export` |
| POST | `/api/privacy/delete-account` |
| GET | `/api/notifications` |
| POST | `/api/notifications/read-all` |
| GET | `/api/integrations` |
| DELETE | `/api/integrations/{integration_id}` |
| GET | `/api/dashboard` |
