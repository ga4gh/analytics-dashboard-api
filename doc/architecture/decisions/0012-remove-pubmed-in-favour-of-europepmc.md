# ADR 0012 — Remove PubMed in Favour of EuropePMC

**Date:** 2025-05

## Status

Accepted

## Context

The dashboard originally included PubMed as a data source for publication and citation data. PubMed data was surfaced through a dedicated backend router, service and repository later and router, consumed by the frontend, and used in Jupyter notebooks to produce combined visualisations alongside GitHub and PyPI data.

EuropePMC has since been adopted as the primary publication data source (ADR 0004). EuropePMC is a superset of PubMed — it indexes PubMed content and additionally covers preprints, books, patents, and literature from the life sciences more broadly. Maintaining both integrations introduces duplication, inconsistency risk, and dead code.

Specific problems with keeping PubMed:

- The PubMed API and web search return different result sets (documented in ADR 0005), creating an unresolved data quality risk
- The `pubmed.py` router, repository and service layer are now effectively unused — all publication data flows through EuropePMC
- Combined dashboard plots that mixed PubMed, PyPI, and GitHub data cannot be maintained consistently when PubMed results are unreliable
- Notebook visualisations that reference PubMed functions will silently produce incomplete results as PubMed queries are no longer curated

## Decision

Remove PubMed entirely from the database, backend, frontend, and notebooks.

**Database**
- Drop the `articles` table (PubMed article records)
- Drop the `authors` table (PubMed author records)
- Drop the `affiliations` table (PubMed affiliation records)
- All publication, author, and affiliation data is now exclusively represented by the `pmc_*` tables sourced from EuropePMC
- Add Liquibase `dropTable` changesets for each table with corresponding `<rollback>` blocks

**Backend (`analytics-dashboard`)**
- Delete `src/routers/pubmed.py`
- Delete `src/services/pubmed.py` and any associated models or schemas
- Remove the SQLAlchemy ORM models for `articles`, `authors`, and `affiliations`
- Remove the `pubmed` router registration from `main.py`
- Remove `PUBMED_API_KEY` from Secrets Manager references and ECS task definition environment

**Frontend (`analytics-dashboard-ui`)**
- Remove all imports and calls to the `/pubmed` API endpoint
- Remove any PubMed-specific Dash components, callbacks, or layout sections
- Update combined plots (cross-source impact views) to use only GitHub and PyPI data

**Notebooks**
- Remove PubMed query cells and associated helper functions
- Update combined visualisation notebooks to source publication data from EuropePMC only
- Remove any notebook dependencies on `PUBMED_API_KEY`

## Consequences

- The codebase is simpler — one fewer external API integration to maintain, test, and credential-rotate
- Three database tables (`articles`, `authors`, `affiliations`) are permanently removed; their data is superseded by the richer `pmc_articles`, `pmc_authors`, and `pmc_affiliations` tables from EuropePMC
- Publication data is exclusively sourced from EuropePMC, which provides broader coverage and a stable, maintained API
- Combined plots (GitHub + PyPI impact) no longer include a PubMed dimension; stakeholders who relied on those views will see EuropePMC data instead where applicable through Analytics Dashboard web version
- `PUBMED_API_KEY` can be removed from Secrets Manager, reducing the credential surface
- Any future need to reference PubMed content is covered by EuropePMC, which indexes all PubMed content
