# ADR-0002: Tenancy enforced in the repository layer; Postgres RLS deferred

- **Status:** accepted · 2026-10-28

## Context
The spec requires every query to be scoped by `user_id` and lists Postgres Row-Level Security as optional defence in depth.

## Decision
Enforce tenancy in `app/repositories.Repo`: every read, update and delete adds `user_id = :current_user`, and foreign ids return 404. An automated sweep (`tests/test_authz_sweep.py`) calls every private route with another user's ids. RLS is not enabled.

## Consequences
One enforcement point, tested on SQLite and Postgres. A raw query that bypasses `Repo` would not be protected, so code review has to reject it. Enabling RLS later needs a per-request `SET app.user_id` and a policy on each table.
