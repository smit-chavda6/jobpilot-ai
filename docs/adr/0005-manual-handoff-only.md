# ADR-0005: Manual hand-off is the only application method

- **Status:** accepted · 2026-10-28

## Context
The spec defines adapter levels `manual_handoff` → `assisted_fill` (Playwright on the user's device) → `api_submit`. None of the permitted sources offers an application-submission API we may use, and assisted filling needs a local browser agent on the user's machine.

## Decision
Ship only `manual_handoff`. After approval, the app opens the employer's page; the user submits there and then confirms in JobPilot. `submitted_confirmed` is reachable only through that confirmation (a state-machine gate), never by opening the form.

## Consequences
No risk of unintended submissions or terms violations. `assisted_fill` and `api_submit` are not implemented, and every source's capability flags say so.
