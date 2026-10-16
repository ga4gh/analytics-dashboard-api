# EPMC Provenance — Table Schemas

Environment legend:
- **[STAGING]** — table exists in the staging database only
- **[PRODUCTION]** — table exists in the production database only
- **[BOTH]** — table exists in both databases (same structure)
- **[NEW]** — column added by this design; does not exist today
- **[MODIFIED]** — existing table with new columns appended

---

## Parent Table (unchanged — included for reference)

`RECORDS` is the root parent of all EuropePMC entities. Every `pmc_articles` row and every
`grants` row holds a FK into `RECORDS`. No columns are added to this table by the provenance
design — it is included here to show the top of the entity hierarchy.

```
RECORDS [BOTH] {
    int          **id**
    string(enum) record_type          
    string(enum) source               
    string(enum) status               
    string[]     keyword
    string(enum) product_line        
    string       created_by
    timestamp    created_at
    string       updated_by
    timestamp    updated_at
    string       deleted_by
    timestamp    deleted_at
    int          version
}
```

---

## Modified Tables

### INGESTION `[MODIFIED]` `[BOTH]`

Adds ingestion-run summary columns. These are written once when the ingestion run completes
and are never updated afterward — `INGESTION` remains append-only.

```
INGESTION [BOTH] {
    int       **id**
    int       version
    timestamp ingested_at
    string    created_by
    timestamp created_at
    int       rows_count
    string    keyword               [NEW] -- EPMC search keyword used for this pull
    string    api_version           [NEW] -- EuropePMC API version (e.g. "6.9")
    int       total_pulled          [NEW] -- total records returned by the EPMC API
    int       new_count             [NEW] -- records classified as NEW (no production match)
    int       unchanged_count       [NEW] -- records classified as UNCHANGED (no diff)
    int       changed_count         [NEW] -- records with a detected diff (auto-approved + queued)
    int       auto_approved_count   [NEW] -- subset of changed: resolved by auto-approve rules
}
```

---

### PMC_ARTICLES `[MODIFIED]`

Two columns added to the **production** table only: who approved this record and when.
In staging, `approved_by` and `approved_at` are always NULL — they carry meaning only after
promotion to production.

```
PMC_ARTICLES [BOTH] {
    int       **id**
    int       record_id             -- FK → records.id
    int       ingestion_id          -- FK → ingestion.id
    string    epmc_id               -- [NEW]
    string    source
    string    pm_id             
    string    pmc_id
    string    full_text_id
    string    doi
    string    title
    int       pub_year
    string    abstract_text
    string    affiliation
    string    publication_status
    string    language
    jsonb     pub_type
    string    is_open_access
    string    inepmc
    string    inpmc
    string    has_pdf
    string    has_book
    string    has_suppl
    int       cited_by_count
    string    has_references
    timestamp date_of_creation
    timestamp first_index_date
    timestamp fulltext_receive_date
    timestamp revision_date
    timestamp epub_date
    timestamp first_publication_date
    string    created_by
    timestamp created_at
    string    updated_by
    timestamp updated_at
    string    deleted_by
    timestamp deleted_at
    int       version
    string    approved_by           [NEW]
    timestamp approved_at           [NEW]
}
```

---

## New Tables — Staging Only

### PMC_REVIEW `[NEW]` `[STAGING]`

One row per article per ingestion run that requires a human decision.
Covers both `review_type = new` (relevance check) and `review_type = changed` (diff review).

```
PMC_REVIEW [STAGING] {
    int       **id**
    int       ingestion_id          -- FK → ingestion.id
    string    epmc_id               -- EuropePMC id (= pmc_articles.epmc_id value)
    string    doi                   -- fallback identifier when epmc_id is absent
    int       staging_article_id    -- FK → pmc_articles.id (staging)
    int       production_article_id -- No FK to production just a record; NULL for NEW records
    string    review_type           -- 'new' | 'changed'
    jsonb     diff_fields           -- structured diff:
                                   --   {
                                   --     "article":      { field: {from, to}, ... },
                                   --     "authors":      [ {match_key, event, changes}, ... ],
                                   --     "affiliations": [ ... ],
                                   --     "citations":    [ ... ],
                                   --     "references":   [ ... ],
                                   --     "fulltexts":    [ ... ],
                                   --     "grants":       [ ... ]
                                   --   }
    bool      auto_approved         -- TRUE if any fields were auto-approved in this run
    string    auto_approve_reason   -- which fields and rules triggered auto-approval
    string    review_status         -- 'pending' | 'approved' | 'rejected' | 'auto_approved'
    string    reviewed_by           -- curator username; NULL while pending
    timestamp reviewed_at           -- NULL while pending
    string    review_comment        -- free-text note from curator (applies to approve or reject)
    string    created_by
    timestamp created_at
}
```

**Indexes:** `(ingestion_id)`, `(epmc_id)`, `(review_status)`, `(reviewed_by)`

**`review_status` values:**

| Value | Meaning |
|---|---|
| `pending` | Awaiting human decision |
| `approved` | Curator accepted the new version — will be promoted to production |
| `rejected` | Curator kept the existing version — field diffs logged to `known_divergences` |
| `auto_approved` | All diffs were handled by auto-approve rules — no human needed |

---

### KNOWN_DIVERGENCES `[NEW]` `[STAGING]`

One row per rejected field change. Prevents the same diff from being re-queued on every
subsequent ingestion where EPMC still shows the rejected value.

```
KNOWN_DIVERGENCES [STAGING] {
    int       **id**
    string    epmc_id               -- EuropePMC id of the article
    string    doi                   -- fallback when epmc_id is absent(might not need it at all)
    string    field_path            -- dot-notation path to the field, e.g.:
                                        -- "article.abstract_text"
                                        -- "authors[orcid:0000-0001-9990-7966].firstname"
                                        -- "affiliations[order:1].org_name"
    string    epmc_value            -- the EPMC value that was rejected (what EPMC said)
    string    retained_value        -- the production value that was kept
    string    rejected_by           -- curator who chose Keep Existing
    timestamp rejected_at           -- when the rejection was recorded
    string    review_comment        -- optional curator note on why this value was rejected
    bool      active                -- TRUE = divergence still applies (EPMC still shows epmc_value)
                                    -- FALSE = EPMC changed to a new value; a fresh diff is now queued
    int       review_id             -- FK → pmc_review.id (the decision that created this row)
    int       ingestion_id          -- FK → ingestion.id (which run triggered the rejection)
    timestamp created_at
}
```

**Indexes:** `(epmc_id, active)`, `(field_path)`, `(review_id)`

**Matching logic:** on every ingestion, for each structural field diff detected:
1. Look up `known_divergences WHERE epmc_id = X`
    `if found`
        `field_path = Y AND epmc_value = Z AND active = TRUE`
2. **Match found** → suppress diff, emit `KNOWN_DIVERGENCE_MATCHED` audit event, do not queue
3. **No match** → queue for review as normal
4. If EPMC later changes to a new value: set old divergence `active = FALSE`, queue fresh diff

---

## New Tables — Both Environments

### EPMC_AUDIT_LOG `[NEW]` `[BOTH]`

One row per business event. Exists in both staging and production — each environment logs
its own events. The `epmc_id` column is the shared key for cross-environment queries.

```
EPMC_AUDIT_LOG [BOTH] {
    int       **id**
    string    event_type            -- see event catalogue below
    string    environment           -- 'staging' | 'production'
    string    entity_type           -- 'article' | 'author' | 'affiliation' | 'citation'
                                    -- | 'reference' | 'fulltext' | 'grant'
                                    -- | 'ingestion' | 'review'
    int       entity_id             -- PK of the affected row in its own table
                                    -- (staging PK for staging events; production PK for production events)
    string    epmc_id               -- EuropePMC id; NULL for ingestion-level events
    string    doi                   -- fallback identifier; NULL when epmc_id is present
    int       ingestion_id          -- FK → ingestion.id
    int       review_id             -- FK → pmc_review.id
    string    performed_by          -- 'system' for auto approved or curator username
    timestamp performed_at
    jsonb     old_value             -- state before the event; NULL for inserts / non-write events
    jsonb     new_value             -- state after the event; NULL for deletions / non-write events
    string    reason                -- system-generated note (e.g. which auto-approve rule fired)
}
```

**Indexes:** `(epmc_id)`, `(ingestion_id)`, `(event_type)`, `(entity_type, entity_id)`, `(performed_at)`

---

**Staging event catalogue:**

| `event_type` | `entity_type` | When emitted |
|---|---|---|
| `INGESTION_STARTED` | `ingestion` | A pull begins |
| `INGESTION_COMPLETED` | `ingestion` | Pull finishes; `metadata` carries all counts |
| `ARTICLE_STAGED` | `article` | A record is written to staging |
| `COMPARISON_NEW` | `article` | No production match found for this epmc_id |
| `COMPARISON_UNCHANGED` | `article` | Staged record matches production exactly |
| `COMPARISON_CHANGED` | `article` | Diff detected; `diff_summary` contains full structured diff |
| `COMPARISON_UNRESOLVABLE` | `article` | No epmc_id or doi present — cannot match |
| `AUTO_APPROVED` | `article` | Auto-approve rules resolved all diffs; no human needed |
| `REVIEW_QUEUED` | `review` | Structural diff queued for human decision |
| `REVIEW_APPROVED` | `review` | Curator accepted the new version |
| `REVIEW_REJECTED` | `review` | Curator kept existing; field diffs logged to `known_divergences` |
| `KNOWN_DIVERGENCE_MATCHED` | `article` | Diff suppressed — matches an active known divergence |
| `KNOWN_DIVERGENCE_EXPIRED` | `article` | EPMC changed beyond the rejected value; divergence deactivated; fresh diff queued |

**Production event catalogue:**

| `event_type` | `entity_type` | When emitted |
|---|---|---|
| `ARTICLE_INSERTED` | `article` | New article written to production |
| `ARTICLE_UPDATED` | `article` | Existing production article replaced; `old_value` + `new_value` captured |
| `AUTHOR_INSERTED` | `author` | New author linked to production article |
| `AUTHOR_UPDATED` | `author` | Author fields changed in production |
| `AUTHOR_REMOVED` | `author` | Author unlinked from production article |
| `AFFILIATION_INSERTED` | `affiliation` | New affiliation written to production |
| `AFFILIATION_UPDATED` | `affiliation` | Affiliation `org_name` changed in production |
| `AFFILIATION_REMOVED` | `affiliation` | Affiliation removed from production |
| `CITATION_INSERTED` | `citation` | New citation linked to production article |
| `CITATION_UPDATED` | `citation` | Citation fields changed in production |
| `CITATION_REMOVED` | `citation` | Citation removed from production |
| `REFERENCE_INSERTED` | `reference` | New reference linked to production article |
| `REFERENCE_UPDATED` | `reference` | Reference fields changed in production |
| `REFERENCE_REMOVED` | `reference` | Reference removed from production |
| `FULLTEXT_INSERTED` | `fulltext` | New fulltext link added to production |
| `FULLTEXT_UPDATED` | `fulltext` | Fulltext availability changed in production |
| `GRANT_INSERTED` | `grant` | New grant linked to production article |
| `GRANT_UPDATED` | `grant` | Grant fields changed in production |
| `MANUAL_EDIT` | `article` / any | Direct change to production outside the pipeline; `ingestion_id` is NULL |

---

## Entity Hierarchy & Table Relationships

```
RECORDS (parent of everything)
    │
    ├── PMC_ARTICLES  (record_id → records.id)
    │       │
    │       ├── PMC_AFFILIATIONS   (article_id → pmc_articles.id)
    │       ├── ARTICLES_AUTHORS   (article_id → pmc_articles.id)
    │       ├── FULLTEXTS          (article_id → pmc_articles.id)
    │       ├── CITATIONS          (article_id → pmc_articles.id)
    │       ├── PMC_REFERENCES     (article_id → pmc_articles.id)
    │       └── PMC_KEYWORDS       (article_id → pmc_articles.id)
    │
    ├── PMC_AUTHORS   (linked via ARTICLES_AUTHORS)
    │
    └── GRANTS        (record_id → records.id)

INGESTION (referenced by all entity tables via ingestion_id)
    │
    ├── PMC_REVIEW         (ingestion_id → ingestion.id)  [STAGING ONLY]
    └── KNOWN_DIVERGENCES  (ingestion_id → ingestion.id)  [STAGING ONLY]

EPMC_AUDIT_LOG (standalone — no FK enforcement; linked by epmc_id + ingestion_id)  [BOTH]
```

---

## Notes

- `pmc_articles` carries three distinct identifiers — they are not interchangeable:
  - `epmc_id` — EuropePMC's own record ID (the `id` field returned by the EPMC API).
  - `pm_id` — PubMed ID (PMID). Assigned by PubMed; absent on preprints and non-PubMed records.
  - `pmc_id` — PubMed Central ID. Present only on articles with a full-text in PMC.

- `doi` is kept as a fallback in all provenance tables. Remove in a future migration if
  operational experience confirms `epmc_id` is always present.

- `PMC_REVIEW.production_article_id` is not a declared FK for the same reason: it references
  a row in the production database from the staging database. Cross-database FK enforcement
  is not possible in PostgreSQL.

- `INGESTION` remains append-only. The new summary columns (`keyword`, `api_version`, counts)
  are written once at `INGESTION_COMPLETED` time and never updated.

- `KNOWN_DIVERGENCES.active` is set to `FALSE` (not deleted) when EPMC changes beyond the
  rejected value. This preserves the audit history of prior rejection decisions.
