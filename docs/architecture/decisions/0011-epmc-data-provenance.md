# ADR 0013 — Data Provenance: EuropePMC Ingestion Versioning (WIP)
 
**Date:** 2026-06

## Context

EuropePMC article data is ingested periodically. Articles can change between ingestions — citation counts update continuously, publication status changes as preprints are accepted, abstracts are corrected, and author lists may be amended.

Without provenance tracking there is no way to answer:
- What changed between ingestion N-1 and ingestion N?
- Which articles are new since last ingestion?
- Was this abstract change deliberate or a data quality issue?
- What did record X look like before the last update?

Stakeholders also need a way to review and approve significant changes (e.g. content corrections) before they are promoted to production, while allowing high-frequency metric changes (citation counts) to flow through automatically.

## Decision

Implement ingestion-level versioning with field-level change tracking:

1. **Every ingestion is assigned an `ingestion_id`** (foreign key from the `ingestion` table). All records created or updated in a given ingestion carry this ID.

2. **A `pmc_article_provenance` table** records one row per changed field per article per ingestion:

| Column | Purpose |
|---|---|
| `ingestion_id` | Which ingestion detected this change |
| `pmc_id` | The article identifier |
| `change_type` | `new_article`, `field_change`, `author_change`, `retracted` |
| `field_name` | Which field changed (NULL for new articles) |
| `old_value` | Value before this ingestion (JSONB) |
| `new_value` | Value after this ingestion (JSONB) |
| `table_name` | Source table |
| `status` | `pending`, `auto_approved`, `approved`, `rejected` |

3. **Auto-approval rules** classify changes without human review:
   - `cited_by_count`, `inepmc`, `inpmc`, `has_pdf`, `has_references` → `auto_approved`
   - `publication_status`, `abstract_text`, `pub_type` → `pending` (requires review)
   - `title`, `pmc_id`, `doi` → blocked and flagged as anomaly

4. **Stakeholder review** is presented as a filtered view of `pending` rows only — unchanged articles produce zero rows and are never shown.

5. **Production promotion** only applies approved and auto-approved changes. Rejected changes are logged but not applied.

## Consequences

- Unchanged articles produce no provenance rows — the delta view shows only what actually changed
- The `ingestion_summary` table pre-aggregates per-ingestion statistics for fast dashboard queries
- Staging and production run the same ingestion with the same `ingestion_id` — staging approval applies to production
- Auto-approval rules are maintained in application code and must be reviewed when new fields are added
- Historical reconstruction requires joining `pmc_article_provenance` rows in `ingestion_id` order from the first INSERT snapshot
