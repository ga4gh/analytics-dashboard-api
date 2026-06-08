# ADR 0012 — Audit Strategy: Unified Audit Log Table

**Date:** 2026-06

## Context

The initial schema implemented a separate `*_audit` table for every main entity table (e.g. `records_audit`, `pmc_articles_audit`, `github_repos_audit`). Each audit table had typed `_before` and `_after` columns for every field in its parent table.

This pattern had the following costs:

- Adding a column to a main table required adding two columns (`_before`, `_after`) to its audit table — a two-changeset operation that is easy to forget
- Querying audit history across tables required 11 separate queries or a large UNION
- Most `_before`/`_after` columns are NULL on any given audit row — only changed fields differ
- `github_repos_audit` alone has over 60 columns

## Decision

Replace all `*_audit` tables with a single `audit_log` table using JSONB for the row snapshots:

| Column | Purpose |
|---|---|
| `id` | Surrogate PK (BIGSERIAL) |
| `action_tstamp` | When the change occurred |
| `action` | `INSERT`, `UPDATE`, or `DELETE` |
| `action_by` | Application user (set via `SET LOCAL app.current_user`) |
| `table_name` | The table that changed (`TG_TABLE_NAME`) |
| `record_id` | PK of the changed row, cast to TEXT |
| `snapshot` | Full row as JSONB — populated on INSERT and DELETE only |
| `changes` | `{"field": {"old": val, "new": val}}` — populated on UPDATE only |

A single PostgreSQL trigger function (`audit_trigger_func`) will be attached to all audited tables. It uses `to_jsonb(OLD)` and `to_jsonb(NEW)` to capture data — no trigger code changes are needed when columns are added or removed.

## Consequences

- Schema changes to main tables never require audit table changes
- A single query retrieves the complete history of any record across all tables
- Storage is reduced: only changed fields are stored on UPDATE; full rows only on INSERT/DELETE
- Type safety on audit queries will be relaxed — field values must be extracted with JSONB operators (`->>`, `->`)
- Point-in-time reconstruction requires replaying INSERT snapshot + UPDATE deltas in sequence
- The previous `*_audit` tables will be dropped in a Liquibase migration changeset
