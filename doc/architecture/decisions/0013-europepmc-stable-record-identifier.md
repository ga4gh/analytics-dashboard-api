# 13. EuropePMC Stable Record Identifier

Date: 2026-07-15

## Status

Accepted

## Context

When designing the curation and audit layer, a stable unique identifier was needed to reliably reference EuropePMC records across ingestion runs, curation events, and audit trails. EuropePMC records contain multiple identifier fields including `pmc_id` and `epmc_id`, which initially appeared to be the most relevant candidates given their naming conventions. These were considered as the primary stable identifiers during early design discussions.

Following direct consultation with the EuropePMC team, it became clear that neither `pmc_id` nor `epmc_id` are guaranteed to be present across all record types. The EuropePMC API exposes its own internal `id` field which is the true stable identifier used by EuropePMC itself to uniquely reference a record regardless of its type or source.

## Decision

Use EuropePMC's own `id` field as the stable unique identifier for all EuropePMC records within the curation and audit system. This field is:

- Present in 100% of records across all record types
- Stable — it does not change after initial assignment
- Authoritative — it is the identifier EuropePMC itself uses internally
- Unique across the EuropePMC dataset

The `id` field will be stored and used as the reference key when linking curation events, audit trail entries, and provenance data back to their source EuropePMC records.

## Consequences

- The `id` field must be captured and stored during EuropePMC data ingestion going forward
- Existing records in the database that were ingested without the `id` field will be backfilled using a standalone Python script. This script will query EuropePMC for each existing record using its other identifiers and populate the `id` field before the provenance work begins
- Once the backfill is complete, the `id` field will be made non-nullable as it is expected to be present for all records
- The curation and audit layer will use `id` as the foreign key reference to EuropePMC records rather than `pmc_id` or `epmc_id`
- Provenance tracking, curation events, and audit trail entries will all be linked to records using `id` as the canonical reference key
- Documentation and API contracts referencing EuropePMC records should use `id` as the canonical identifier going forward
