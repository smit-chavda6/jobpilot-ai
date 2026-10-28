# Runbook

Operational procedures for a self-hosted JobPilot AI stack (Docker Compose). Commands assume the
repository root.

## Start, stop, upgrade

```bash
docker compose up --build -d     # start or upgrade (the api container runs `alembic upgrade head` on boot)
docker compose ps                # api/web/postgres should be "healthy"; the worker has no healthcheck
docker compose logs -f api worker
docker compose down              # stop (data kept in the pgdata/uploads volumes)
```

Health: `GET /healthz` (liveness), `GET /api/readyz` (DB reachable, active AI provider).

## Backup

Back up the database and the uploads volume together. Resumes are referenced by storage key.

```bash
docker compose exec -T postgres pg_dump -U jobpilot -Fc jobpilot > backup-$(date +%F).dump
docker run --rm -v jobpilot_uploads:/data -v "$PWD":/out alpine tar czf /out/uploads-$(date +%F).tgz -C /data .
```

Restore into a fresh stack:

```bash
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U jobpilot -d jobpilot --clean --if-exists < backup-YYYY-MM-DD.dump
docker run --rm -v jobpilot_uploads:/data -v "$PWD":/in alpine tar xzf /in/uploads-YYYY-MM-DD.tgz -C /data
docker compose up -d
```

Backups contain personal data. Encrypt them at rest and apply the same retention you promise users.
A restored backup brings back accounts that were deleted after it was taken: re-run those deletions.

## Key rotation

**`JWT_SECRET`** signs access tokens only (refresh tokens are opaque and stored hashed). Changing it
invalidates current access tokens, but the SPA refreshes transparently, so users stay signed in.
Change the value in `.env`, then run `docker compose up -d api worker`.

**`ENCRYPTION_KEY`** wraps the per-field data keys used for encrypted fields (phone number,
integration tokens). Each value is stored as `{wrapped data key, ciphertext}`, so rotation means
re-wrapping the data keys:

1. Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. With the stack stopped, run a one-off re-wrap: for each encrypted column, decrypt with the old key
   and encrypt with the new (`app.security.crypto.decrypt_field` / `encrypt_field`).
3. Put the new key in `.env` and start the stack.

There is no automated re-wrap command in this build (see STATUS.md). Until there is, do step 2 with
a short script under `apps/api/scripts/` and test it on a backup first.

**AI provider keys:** replace `OPENAI_API_KEY` / `GEMINI_API_KEY` and restart `api` and `worker`.
Revoke the old key with the provider.

## Incident handling

1. **Contain.** For suspected token theft, rotate `JWT_SECRET`. For a compromised account, have the
   user reset their password. For a suspicious source, disable it with `SOURCE_*_ENABLED=false`.
   For runaway AI spend, set `LLM_PROVIDER=mock` or lower `AI_DAILY_TOKEN_BUDGET_GLOBAL`.
2. **Investigate.** Logs are JSON, PII-redacted, with `request_id`, which is also returned to clients
   as `X-Request-ID` and shown in error envelopes. The `audit_logs` table records registrations,
   logins, re-auth, consent changes, approvals, submission confirmations, exports and integration
   changes. `ai_usage_logs` records provider, model, prompt version, tokens, latency and outcome per call.
3. **Recover.** Restore from backup if data was altered. If the scoring config changed, users can
   re-score from the Jobs page (`POST /api/matches/rescore`).
4. **Notify.** If personal data was exposed, notify affected users and regulators within the
   timelines your jurisdiction requires (e.g. 72 hours under GDPR; India's DPDP Act and Rules).
5. **Learn.** Add a regression test and update `docs/threat-model.md`.

## Common operational issues

| Symptom | Check |
|---|---|
| Jobs stay "Scoring in progress" | `docker compose logs worker`. Unprocessed rows in `outbox_events` (`processed_at IS NULL`) show a backlog. |
| Reminders not firing | Is the worker running? Reminders fire on its 60-second periodic pass. |
| 429s for one user | Rate limits are per process and in memory; restarting `api` clears them. |
| Data subject request | The user can export (Settings → Export my data) and delete (Settings → Delete account) without an operator. The deletion response is a verification report. |
