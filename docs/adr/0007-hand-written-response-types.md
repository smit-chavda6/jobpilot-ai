# ADR-0007: OpenAPI contract exported; frontend response types written by hand

- **Status:** accepted · 2026-10-28

## Context
The spec asks for a frontend API client generated from the OpenAPI schema with openapi-typescript. Most endpoints return documented dictionaries rather than Pydantic response models, so generated response types would be untyped objects.

## Decision
Export the schema to `packages/contracts/openapi.json` (`make openapi`, which also runs `npm run gen:api` to produce `src/api/schema.d.ts`). Response shapes are typed by hand in `apps/web/src/api/types.ts`, checked against responses captured from the running API. The Playwright journey exercises them end to end.

## Consequences
Response types can drift if the API changes without a matching frontend change. Adding Pydantic response models to the routers would let generated types replace the hand-written ones.
