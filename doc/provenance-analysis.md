# EPMC Provenance & Curation Layer — Design Analysis

**Document:** epmc-data-provenance-plan.md  
**Status:** Pre-implementation review  
**Reviewed:** August 2026

---

## 0. Known Data Quality Issues (Observed August 2026)

Before implementation begins, the following was confirmed on the live staging database:

| Metric | Value |
|---|---|
| Total rows in `pmc_articles` | 2,532 |
| Distinct articles by `pm_id` | 1,284 |
| Distinct articles by `doi` | 1,240 |
| Ingestion runs | 20 (April 6 – July 30 2026) |

**Every article exists as exactly 2 rows** — the ingestion pipeline re-inserts all records on every run with no deduplication. 44 articles have a shared or missing DOI (preprints that later received a journal DOI).

**Impact on production setup:** the local production DB (`analytics_prod_local`) requires a one-time dedup before the system-approval stamp — keeping the latest row per `pm_id` by `ingestion_id DESC`. This is automated in `scripts/setup_local_dbs.sh`.

**Impact on the provenance plan:** the auto-classify service must deduplicate staging records before comparison. Comparing 2,532 staged rows against 1,284 production rows without dedup will produce false positives — the classifier will see the older ingestion copy as a "changed" record against the newer production row.

---

## 1. Database Changes

The plan introduces a two-environment schema split (staging / production) with three new tables and column additions to two existing tables. The biggest gap between current state and the plan is that `epmc_id` does not exist anywhere in the live schema today.

### Modified Tables

| Table | Environment | Columns Added | Notes |
|---|---|---|---|
| `pmc_articles` | Both | `epmc_id`, `approved_by`, `approved_at` | `approved_by/at` meaningful only in production; always NULL in staging |
| `ingestion` | Both | `keyword`, `api_version`, `total_pulled`, `new_count`, `unchanged_count`, `changed_count`, `auto_approved_count`, `pending_review_count` | Written once at `INGESTION_COMPLETED`; table remains append-only |

### New Tables

| Table | Environment | Purpose |
|---|---|---|
| `pmc_review` | Staging only | Review queue — one row per article per ingestion run requiring human decision. Stores structured diff as JSONB across all entity types |
| `known_divergences` | Staging only | Rejected-change registry. Suppresses re-surfacing of already-reviewed diffs when EPMC still shows the same rejected value |
| `epmc_audit_log` | Both | Business event log. Staging captures ingestion + review lifecycle; production captures every write. Linked by `epmc_id` |

### Critical Gap — `epmc_id` Not Stored Today

> **BLOCKING:** The entire matching strategy (NEW / UNCHANGED / CHANGED classification) depends on `epmc_id` as the primary key. This column does not exist in the live `pmc_articles` table. The current code uses `pm_id` (PubMed ID), which is absent on preprints. A Liquibase migration and a one-time data backfill — either from re-pulling EPMC or from an `id → pm_id` mapping query — are required before any classification logic can run.

Current live schema (relevant columns):
```
pmc_articles
  pm_id               -- used as match key today
  pmc_id
  doi
  title, abstract_text, pub_year …
  -- epmc_id: MISSING (needed as primary stable identifier)
  -- approved_by: MISSING
  -- approved_at: MISSING
```

### Existing Audit Table Coverage

The current schema has trigger-based audit tables for `affiliations`, `pypi`, `pypi_versions`, `github_repos`, `records`, `articles`, `authors`, and `keywords`. **There are no trigger-based audit tables for any `pmc_*` table** — `pmc_articles`, `pmc_authors`, `pmc_affiliations`, `articles_authors`, `citations`, `pmc_references`, `fulltexts`, or `grants`.

The plan's `epmc_audit_log` replaces this for business events, but direct DB edits outside the API will not be captured unless the caller explicitly writes a `MANUAL_EDIT` event.

### Liquibase Complexity

With two databases sharing most but not all of the schema, migrations need:
- A **shared changelog** for tables that exist in both environments (`pmc_articles` columns, `ingestion` columns, `epmc_audit_log`)
- A **staging-only changelog** for `pmc_review` and `known_divergences`
- A **production-only safeguard** ensuring `approved_by/at` are never written from the staging pipeline

---

## 2. Code Changes

The plan's scope is broader than the "pipeline between EPMC API and production DB" framing suggests. It requires new services, new API surface, schema model updates, and a fundamental change to how the backend connects to databases.

### New SQLAlchemy Models

| Model | Notes |
|---|---|
| `PMCReview` | New. `diff_fields` as JSONB with nested structure across all entity types |
| `KnownDivergence` | New. `field_path` uses dot-notation strings like `authors[orcid:x].firstname` |
| `EPMCAuditLog` | New. Shared between staging and production with `environment` column discriminator |
| `PMCArticle` | Modified. Add `epmc_id`, `approved_by`, `approved_at` |
| `Ingestion` | Modified. Add 8 summary count columns |

### New Services

| Service | Responsibility | Complexity |
|---|---|---|
| `AutoClassifyService` | After every ingestion: compare each staged article vs production by `epmc_id`, compute structured diff across all entity types, check `known_divergences`, apply auto-approve rules, write to `pmc_review` | High — child entity diffing (authors, citations) requires stable ID matching |
| `PromotionService` | Write approved staging record to production DB; fire production audit events; update `approved_by/at` | Medium — needs transactional write across two DB connections |
| `ReviewExportService` | Serialize review queue to Excel with full diff per article; re-import decisions in bulk | Medium — Excel schema must be versioned; re-import needs conflict detection |

### New API Endpoints

```
GET  /staging/review-queue          -- paginated queue; filterable by status, ingestion_id
POST /staging/{epmc_id}/approve     -- curator approves; triggers PromotionService
POST /staging/{epmc_id}/reject      -- curator rejects; writes to known_divergences
GET  /staging/review-queue/export   -- returns .xlsx with full diff per article
POST /staging/review-queue/import   -- bulk decision re-import from Excel
GET  /staging/ingestion-summary     -- counts per ingestion run (new/unchanged/changed/pending)
```

### Two-Database Architecture — Unaddressed in Plan

> **CRITICAL GAP:** The plan does not address how the backend connects to both staging and production databases simultaneously. Currently the backend has a single `DATABASE_URL` environment variable and a single SQLAlchemy session. The promotion service needs to write to production while classification reads from staging. The dashboard-serving endpoints (`/epmc/all-articles`, KPIs, charts) must read from **production only**. This requires either two separate SQLAlchemy engines with session routing, or two separate backend services (one per DB).

Practical v1 approach: two env vars (`STAGING_DATABASE_URL`, `PRODUCTION_DATABASE_URL`) and a FastAPI dependency that selects the session by endpoint prefix (`/staging/*` → staging session, all others → production session).

### Modified Ingestion Endpoint

`POST /epmc/ingest-pmc-data` currently writes records and returns. After this change it must:
1. Pull from EPMC API → write all records to staging DB
2. Call `AutoClassifyService` per record
3. Write summary counts to `ingestion` row at completion
4. Fire `INGESTION_COMPLETED` audit event

Steps 2–4 are synchronous in the current design. For 1,284+ articles this will make the endpoint take minutes. A task queue (Celery, ARQ, or AWS SQS) should be considered so the endpoint returns immediately and classification runs asynchronously.

### Dashboard / Frontend Impact

> The plan states "No change to dashboard/frontend." This is true for UI code — but it assumes the backend serving dashboard data is reconfigured to point at the **production** database. Today's deployment points the ECS backend task at the staging DB. After the split, KPI counts, charts, and tables must all read from production. Any article in staging that hasn't been curator-approved will disappear from the dashboard until approved.

---

## 3. Auditing

The plan introduces a coherent business-event audit model via `epmc_audit_log`, capturing *why* something changed alongside *what* changed. It sits alongside, not replacing, the existing trigger-based audit tables.

### Two Audit Systems — Coexistence

| System | Mechanism | Tables covered today | Captures |
|---|---|---|---|
| Trigger-based audit tables | DB triggers on INSERT/UPDATE/DELETE | `affiliations`, `pypi`, `github_repos`, `records`, `articles`, `authors`, `keywords` | Every row-level change with before/after columns. Does NOT cover any `pmc_*` tables |
| `epmc_audit_log` | Application-layer events via `PromotionService` / ingestion pipeline | All `pmc_*` entities (new) | Business events with `old_value`/`new_value` JSONB, `performed_by`, `review_id`, `reason`. Does NOT fire on direct DB edits |

### Identity — Who Is the Curator?

> Every audit row captures `performed_by` (curator username). The current system has no authentication layer — the backend is a public API. Before review endpoints go live, an auth mechanism is required. Without it, `reviewed_by` in `pmc_review` and `performed_by` in `epmc_audit_log` are whatever the caller sends in the request body — unverifiable and self-reported.

### Cross-Environment Querying

For v1, querying across two separate RDS instances requires an application-layer merge: an export endpoint that fetches from both `epmc_audit_log` tables and merges on `epmc_id`. A future FDW or Aurora global cluster is out of scope.

### Known Divergence Deactivation Audit

When `active` is set to `FALSE` on a `known_divergences` row (because EPMC changed to a new value), the `KNOWN_DIVERGENCE_EXPIRED` audit event must be explicitly written by `AutoClassifyService`. This should be enforced in code, not left to convention.

---

## 4. Bottlenecks

> **Update (August 2026):** The original plan assumed a full re-pull every ingestion run with `revision_date` used for change detection. The EPMC team confirmed this is incorrect — `revision_date` is publisher-controlled and unreliable. The correct approach is EPMC's `UPDATE_DATE` query parameter, which returns only records updated in EPMC since a given date. `epmc-data-provenance-plan.md` has been updated to reflect delta ingestion. This eliminates the Critical O(N) bottleneck below for all but the first run and periodic full reconciliations.

| Severity | Bottleneck | Detail |
|---|---|---|
| ~~Critical~~ **Mitigated** | ~~Full re-pull classification is O(N × DB lookups)~~ Delta pull is O(K × DB lookups) | **Original:** 1,284 articles × DB lookups per run. **Revised (delta ingestion):** Only articles updated since last ingestion run are pulled using `UPDATE_DATE:[last_fetch TO today]`. K (daily delta) is typically tens to hundreds of records. The first full-sync run and monthly reconciliation runs still process all 1,284+ articles — a task queue should be used for those. |
| Critical | Child entity diffing without stable IDs | Authors, affiliations, citations are lists with no stable per-child ID across EPMC pulls. `known_divergences` field path notation (`authors[orcid:X].firstname`) assumes ORCID presence — many authors have none. Without ORCID, fallback to name is unstable. Author list diffing is an O(n²) fuzzy match problem and the most complex part of the classifier. |
| Medium | Review queue accumulation across ingestion runs | If ingestion runs weekly and curators review monthly, the queue grows continuously. New ingestion runs create new `pmc_review` rows for articles already pending from prior runs. No auto-escalation path or queue-depth alert is defined. |
| Medium | Ingestion atomicity — partial classification state | If `AutoClassifyService` crashes after processing 600 of 1,284 articles, summary counts are never written and the queue is half-populated. Needs transaction boundary with idempotency by `ingestion_id`. |
| Medium | `known_divergences` grows unbounded | Inactive rows (`active = FALSE`) are never deleted per the plan — preserved for audit history. Over years with EPMC continuously updating abstracts, this table could contain thousands of inactive rows per article. Plan archival strategy now. |
| Low | Excel re-import without conflict detection | If a curator exports the queue, reviews offline, and imports — but another curator approved/rejected some rows in the meantime — the re-import has no conflict resolution. Must check each row is still `pending` before applying the imported decision. |

---

## 5. Where the Plan Could Fail

### Design Assumptions That May Not Hold

**1 — One-time migration cannot populate `epmc_id` reliably** *(Critical)*  
The migration plan is "set `approved_by = 'system'` on the latest version per `id`." But existing rows don't have `epmc_id` stored — the ingestion pipeline never captured it. To backfill, each row must be re-matched to a live EPMC record. If EPMC no longer returns some older records (retracted, ID-changed), those rows become unresolvable. Verify EPMC API returns IDs for all existing `pm_id` values before writing the migration.

**2 — Dashboard goes dark between ingestion and curator approval** *(Critical)*  
Once the dashboard reads from production only, newly ingested articles are invisible until approved. If the review queue takes two weeks to clear, new GA4GH publications won't appear on the dashboard for two weeks. Stakeholders need to understand this trade-off. Consider surfacing a "pending review" count on the dashboard.

**3 — Citation count noise creates review queue pollution** *(Medium)*  
The plan auto-approves `cited_by_count` increases but sends decreases to human review. EPMC citation counts fluctuate by ±1–3 on nearly every ingestion due to deduplication changes and source corrections — not retractions. Without a minimum threshold (e.g. decrease ≥5), the review queue will be dominated by citation count noise on every run.

**4 — Preprint → published article creates duplicate NEW records** *(Medium)*  
If the preprint and the published article have different DOIs (common — bioRxiv vs. journal), neither `epmc_id` nor DOI will match between them. Both will be classified as NEW independently. The curator will see two records for the same paper with no automated link.

**5 — Single reviewer with no auth is an unenforceable audit trail** *(Medium)*  
Without authentication, `reviewed_by` is whatever the caller sends. Even HTTP Basic auth or a per-curator API key is required for `performed_by` to have evidentiary value.

**6 — Concurrent ingestion runs create duplicate staging rows** *(Low)*  
If the ingest endpoint is called twice before the first completes, both runs classify the same articles independently and create two `pmc_review` rows with the same `epmc_id`. Add a unique constraint on `(epmc_id, ingestion_id)` in `pmc_review` and an idempotency check at classification start.

**7 — Auto-approve field list breaks silently on EPMC API changes** *(Low)*  
If EPMC adds or renames fields, the classifier silently misses new fields or raises on unexpected keys. An explicit API version check at ingestion start — compared against the version the classifier was built for — would surface this proactively.

---

## Pre-Implementation Checklist

| # | Issue | Action |
|---|---|---|
| 1 | `epmc_id` backfill strategy | Verify EPMC API returns IDs for all existing `pm_id` values before writing migration |
| 2 | Two-DB architecture | Define session routing strategy in FastAPI before any service code is written |
| 3 | Auth for review endpoints | Decide on auth mechanism (API key minimum) before review API ships |
| 4 | Classification performance | Design task queue integration before synchronous ingestion becomes unusable |
| 5 | Author child diffing | Define stable ID fallback when ORCID is absent — hardest classification problem |
| 6 | Citation count threshold | Add minimum-delta rule to auto-approve small citation count decreases |
| 7 | Dashboard lag transparency | Surface "pending review" count so stakeholders understand delay |
