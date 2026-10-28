# ADR-0004: Embeddings stored as JSON, cosine similarity in Python (no pgvector yet)

- **Status:** accepted · 2026-10-28

## Context
The spec asks for pgvector with an HNSW index for the 10% semantic component and for semantic search (P1).

## Decision
`job_embeddings.vector` is a JSON array with `model` and `dim` recorded. Similarity is computed in Python against the user's profile embedding when a job is scored. The semantic weight is capped, so it can't rescue an ineligible job.

## Consequences
Behaves identically on SQLite and Postgres, and per-user job counts are small enough for linear scans. pgvector/HNSW and semantic search are **not implemented** (listed in STATUS.md). Migrating means adding the extension, a `vector(dim)` column, a backfill and an HNSW index.
