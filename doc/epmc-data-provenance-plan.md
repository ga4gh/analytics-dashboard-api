# Europe PMC (EPMC) Data Curation & Provenance

## Design Proposal — GA4GH Analytics Dashboard

**Prepared by:** Dashrath Chauhan

**Date:** June 2026

**Status:** For TT internal review followed by stakeholders input

---

# The Problem

EuropePMC records are not static. Titles get corrected, abstracts are revised, publication statuses change, and citation counts update continuously — all outside our control.

**What this means for the dashboard pipeline today:**

- Data ingested into our database may silently change between ingestion runs
- Our pipeline has no record of what changed, when it changed, or whether it was reviewed before reaching the dashboard
- There is no way for a curator to intervene before changed data reaches the dashboard
- We cannot answer basic questions like _"how many new publications appeared in the latest pull?"_ or _"was this article relevant before it was added?"_

The core issue is not data freshness — it is **auditability, explainability, and curation control**.

---

# Current Process

```
  Europe PMC API
       │
       ▼
  Pull all articles
       │
       │    ← no diff, no review, no history   
       ▼                
  Insert into database
  (all records, every run)
       │
       ▼
  Dashboard (live query)
```

**Limitations:**
- Every ingestions re-inserts all records - new and existing
- No mechanism to identify which records are genuinely new vs re-inserted unchanged
- No human checkpoint/review before visualisations
- No stack trace - impossible to trace what has changed over time for a specific record

---

# What We Need

1. Staging area - **already have**
     - A database of Europe PMC records in our control
2. Audit trail - **missing**
     - Record of what, when, who changed and approved it
3. Curation layer - **missing**
     - Humar review before changes surfaced on dashboard
4. Separate instance for staging and production - **partially missing**
     - DB instances
          1. Staging db - **already have**
          2. Production db - **missing**
     - Domains/instances
          1. https://analytics-staging.ga4gh.org - **already have**
          2. https://analytics.ga4gh.org - **missing**


---

# Proposed Architecture

```
  Europe PMC API
       │
       ▼
  ┌────────────────────────────────────────────────────────┐
  │  STAGING DATABASE                                      │
  │  All records written here on every pull                │
  │                                                        │
  │  Step 1 — Auto-classify each record:                   │
  │  ┌──────────┬───────────┬──────────────────────┐       │
  │  │  NEW     │ UNCHANGED │       CHANGED        │       │
  │  │ no match │  no diff  │    diff detected     │       │
  │  └────┬─────┴─────┬─────┴──────────┬───────────┘       │
  │       │           │                │                   │
  │       │           │   Step 2 — Check diff type:        │
  │       │           │         ┌──────┴──────┐            │
  │       │           │    Metric fields   Structural      │
  │       │           │    (count/flag)     fields         │
  │       │           │         │              │           │
  │       │           │    Auto-approve   Step 3 —         │
  │       │           │         │         Known divergence?│
  │       │           │         │              │           │
  │       │           │         │       ┌──────┴─────┐     │
  │       │           │         │    Match        No match │
  │       │           │         │   Suppress        Queue  │
  │       │           │         │   (log only)             │
  └───────│───────────│─────────│──────────────────────────┘
          │           │         │              │
          ▼           ▼         ▼              ▼
    Review queue   Log only  Log only     Review queue
    (relevance)   (no action)(auto-approved)(diff review)
          │                                   │
          └──────────────┬────────────────────┘
                         ▼
                  Human decision
                  Approve / Keep existing
                         │
                         ▼
             ┌───────────────────────────┐
             │  PRODUCTION DATABASE      │
             │  Curated, approved data   │
             │  approved_by / approved_at│
             └───────────────────────────┘
                         │
                         ▼
                  Dashboard / API
```

---
# Staging Paths
## Path 1 — NEW Record

No matching record exists in the production database (no PMID or DOI match).

**Action: Queue for relevance review.**

The record lands in `pmc_review` with `review_type = new`.
A curator checks: _is this article genuinely relevant to GA4GH?_

 - **Approve** - Record promoted to production. Marked with `approved_by` and `approved_at`. 
 - **Reject** - Record stays in staging only. Rejection reason logged.

> [!IMPORTANT]
> A keyword match is not a relevance guarantee. All new records require human sign-off before reaching the dashboard.

---

## Path 2 — UNCHANGED Record

A matching record exists in production. Field-by-field comparison finds no differences.

**Action: Log it and move on. No promotion, no review.**

The ingestion audit records that the article was seen and unchanged. Nothing else happens.

---

## Path 3 — CHANGED Record

A matching record exists in production. One or more fields differ.

**Action: Compute the diff. Apply auto-approve rules (if any). Queue structural changes for human review.**

The diff is split into two categories(This will be changed based on stakeholders feedback - if no auto approve fields, every change will go through human review):
- **Metric fields** - `cited_by_count`, additive flag changes (`N→Y` only) 
     - **Action** → Auto-approved — low risk, no human needed
- **Structural fields** - `title`, `abstract_text`, `publication_status`, `authors`, `affiliations`, `doi`, and all other fields 
     - **Action** → Queued for human review

---

# The Review Workflow

When a record reaches the review queue, a curator sees the full diff:

```
Field               Production (current)        Staged (new from EPMC)
────────────────────────────────────────────────────────────────────────────
abstract_text       "Some abstract"           "Some changed abstract"   ← changed
cited_by_count      47                                52                ← auto-approved
title               (unchanged)
doi                 (unchanged)
authors             (unchanged)
```

The curator makes one decision:
1. **Accept new version:** 
     1. New record promoted/updated to production 
     2. approved_by and approved_at updated
     3. Audit logged

     OR
2. **Keep existing:** 
     1. Staged record will be added to known_divergence. 
     2. Will be matched with _**known_divergence**_ on next ingestion, if there is an exact match on changed fields it will ignore the change and won’t add to review queue.


---

# Preventing Re-surfaced Rejections — Known Divergences (Chen's Idea)

**The problem:** If a curator rejects the change and decides to keep existing version, the next ingestion might detect same changes again and add it to review queue. This will need review again and a waste of time.

**The solution:** `known_divergences` table.

When a curator selects "Keep existing", the specific field name + the EPMC value that was rejected are stored:

```
id:          "32485260"
field_path:     "article.abstract_text"
epmc_value:     "Some text"
retained_value: "Some changed text"
rejected_by:    "dashrath"
active:         TRUE
```

**On the next ingestion:** if the same diff is detected for the same field and the same EPMC value → it matches a known divergence → it is suppressed silently. The audit log records `KNOWN_DIVERGENCE_MATCHED`.

**If EPMC changes again** beyond the rejected value → the known divergence is marked `active = FALSE` → the new diff is surfaced for fresh review.

**Example:**
**Ingestion #5** — EPMC abstract changes; curator reviews and says Keep Existing.
```
known_divergences: field=abstract_text, epmc_value="Some Changed text", active=TRUE
```
 
**Ingestion #6** — EPMC returns the same changed value.
```
epmc_value matches known_divergences → SUPPRESS → no review noise
```
 
**Ingestion #7** — EPMC changes to a third value.
```
epmc_value does NOT match known_divergences (different value)
→ mark old divergence active=FALSE
→ queue new diff for review
```

---

# Auto-Approve Rules — v1 (Jimmy mentioned this descision should come from stakeholders so will be updated or removed based on thier feedback)

Certain low-risk changes are automatically approved without human review. These are included in v1.

| Field | Condition | Reason |
|---|---|---|
| `cited_by_count` | New value > current value | Citation counts only increase; tracking is informational |
| `inepmc` | `N → Y` only | Additive — the article became available in EPMC full text |
| `inpmc` | `N → Y` only | Additive — the article became available in PubMed Central |
| `has_pdf` | `N → Y` only | Additive — a PDF became available |
| `has_book` | `N → Y` only | Additive — book version became available |
| `has_suppl` | `N → Y` only | Additive — supplementary data became available |

**What is NOT auto-approved (always requires human review):**
- Any flag change from `Y → N` (something was retracted or removed)
- `cited_by_count` decrease (unusual, may indicate retraction)
- Any structural field: `title`, `abstract_text`, `publication_status`, `doi`, `authors`, `affiliations`, `citations`, `references`, `fulltexts`, `grants`


---

# The Audit Trail

Every action on every record is logged to `epmc_audit_log`. This table exists in **both** staging and production databases.

**Staging audit log** captures the full ingestion and review workflow:

| Event | Triggered when |
|---|---|
| `INGESTION_STARTED` | Ingestion start |
| `INGESTION_COMPLETED` | Ingestion complete — with counts (new/unchanged/changed/auto-approved/pending) |
| `ARTICLE_STAGED` | A record is written to staging |
| `COMPARISON_NEW` | No production match found |
| `COMPARISON_UNCHANGED` | Record matches production exactly |
| `COMPARISON_CHANGED` | Diff detected — includes the full structured diff |
| `COMPARISON_UNRESOLVABLE` | No PMID or DOI present |
| `AUTO_APPROVED` | Auto-approve rule applied — includes which rule and what changed |
| `REVIEW_QUEUED` | Sent to human review queue |
| `REVIEW_APPROVED` | Curator approved the new version |
| `REVIEW_REJECTED` | Curator kept the existing version |
| `KNOWN_DIVERGENCE_MATCHED` | Diff suppressed — matches a prior rejection |
| `KNOWN_DIVERGENCE_EXPIRED` | EPMC changed again — prior rejection no longer covers it, active=FALSE |

---

**Production audit log** captures every write to the production database:

| Event | Triggered when |
|---|---|
| `ARTICLE_INSERTED` | New article in production |
| `ARTICLE_UPDATED` | An existing production article is updated |
| `CHILD_INSERTED` | New child entiry (author, citation, grant, etc.) |
| `CHILD_UPDATED` | Child entry updated |
| `CHILD_REMOVED` | Child entity removed from Production |

**CHILD keys can be changed to capture more granular audits like AUTHOR_UPDATED or AFFILIATION_UPDATED.**

**Key columns on every audit row:** `id`, `entity_type`, `ingestion_id`, `review_id`, `performed_by`, `performed_at`, `old_value` (JSONB), `new_value` (JSONB), `diff_summary` (JSONB), `reason`

**Using `id`** from PMC API, the full history of any article can be reconstructed across both environments

---

# Database Schema — Staging

Staging holds the full set of entity tables (same structure as production) plus three additional tables:

**Entity tables (same schema as production):**
`pmc_articles`, `pmc_authors`, `pmc_affiliations`, `articles_authors`, `citations`, `pmc_references`, `fulltexts`, `grants`, `records`

**Modified table:**

| Table | Changes from current |
|---|---|
| `ingestion` | Add: `keyword`, `api_version`, `total_pulled`, `new_count`, `unchanged_count`, `changed_count`, `auto_approved_count`, `pending_review_count`, `unresolvable_count` |

**New tables:**

| Table | Purpose |
|---|---|
| `pmc_review` | Review queue — one row per article requiring human decision. Contains `diff_fields` JSONB with structured diff across all entity types, `review_type` (new/changed), `review_status` (pending/approved/rejected/auto_approved), `reviewed_by`, `reviewed_at`, `rejection_reason` |
| `known_divergences` | Rejected change log — suppresses re-surfacing of already-reviewed rejections. Contains `field_path`, `epmc_value`, `retained_value`, `active` |
| `epmc_audit_log` | Full business event history for every action in staging |

---

# Database Schema — Production

Production holds only curated, approved data. No flags, no staging artefacts.

**Entity tables:**
`pmc_articles`, `pmc_authors`, `pmc_affiliations`, `articles_authors`, `citations`, `pmc_references`, `fulltexts`, `grants`, `records`

**Modified table:**

| Table | Changes from current |
|---|---|
| `pmc_articles` | Add: `approved_by VARCHAR(64)`, `approved_at TIMESTAMPTZ` |

**New table:**

| Table | Purpose |
|---|---|
| `epmc_audit_log` | Full business event history for every write to production |

**What production does NOT have:**
- No `to_use` flag — every record in production is active by definition. There is only one version per article.
- No `pmc_review` or `known_divergences` — these are staging-only concepts.

**ER Diagram of new schema is available here (WIP)**
---

# Matching Records Across Pulls using Stable Identifier

To compare a staged record against production, we need a stable identifier.

**Primary match key: PMC ID (ID)**
- Assigned by Europe PMC and does not change
- Present on all indexed journal articles including preprints
- Stored as `id` in the database

**Fallback: DOI**
- Used when ID is absent
- Less stable than ID but sufficient as a fallback

**Edge case — preprint to published article:**
A preprint (no ID, matched by DOI) later receives a ID.
On the next pull it is matched by DOI. The status change (`preprint → published`) and any other field changes surface in the review queue. The curator approves. Lineage is preserved through the staging audit history. Subsequent matches will be done using `id`.

**Edge case — unresolvable record (Rare case):**
A record with neither ID nor DOI is classified as `COMPARISON_UNRESOLVABLE`. It is flagged for manual handling and does not enter the review queue automatically.

> **Open question:** Is there any record where neither id nor doi is present in current dataset?
     
> No - every record have both id and doi

---

# Sign-off Model

**Proposed for v1: Single reviewer sign-off.**

- Single reviewer makes the decision
- Identity and action are recorded on every action


**Reserved for later: Two-step approval.**
- Reviewer do record-by-record review
- Second reviewer does a final sign off
- This could be managed by a flag, no complicated schema changes needed


> **Open question:** Is single reviewer sign-off acceptable for v1, or is two-step approval required from the start?

---

# Review process

**Excel export for offline review:**

The review queue can be exported to Excel for reviewers who prefer bulk offline review. The export includes the full diff per article. Decisions (approve / keep existing) and reasons are recorded in the spreadsheet and re-imported to update `pmc_review` rows in bulk.

This avoids the need for a review UI in v1 while still supporting non-technical reviewers.

---

# What Does Not Change

| Area | Impact |
|---|---|
| Dashboard / frontend | No change.|
| EuropePMC API integration | New APIs and business logic to integrate review and approval flow. |
| GitHub / PyPI data | No change. we will target Europe PMC for this iteration and extend the same mechanism for other sources (can target for Plenary if time permits). |
| Ingestion endpoint | No change. Same `POST /epmc/ingest-pmc-data` call. |
| Existing production records | One-time migration: `approved_by = 'system'`, `approved_at = ingested_at` for all current records. Lineage starts from this point forward. |

The change is entirely in the **pipeline between the Europe PMC API and the production database**.

---

# Technical Scope

### New infrastructure for v1:

| Component | Description |
|---|---|
| Staging database | Separate DB with full entity tables + `pmc_review` + `known_divergences` + `epmc_audit_log` |
| Auto-classify service | Runs after every ingestion pull — compares staging vs production, applies auto-approve rules, populates review queue |
| Review API endpoints | `GET /staging/review-queue`, `POST /staging/{id}/approve`, `POST /staging/{id}/reject`, `GET /staging/review-queue/export` |
| Promotion service | Writes approved staging records to production, fires production audit events |
| Production audit log | `epmc_audit_log` table + write events on every production change |

### Not in scope for v1:

| Item | Reason deferred |
|---|---|
| Review UI | v1 uses API + Excel export; UI is a natural follow-on |
| Extended auto-approve rules | More rules can be added once the first curated decisions are accumulated |

---

# Open Questions — Requiring Confirmation

| # | Question | Proposed default | Status |
|---|---|---|---|
| 1 | ID + DOI sufficient as match key strategy? | Yes — ID primary, DOI fallback | **Open** |
| 2 | Single reviewer sign-off for v1? | Yes | **Open** |
| 3 | Single shared review queue for v1? | Yes | **Open** |
| 4 | NEW records go to review queue (not auto-promoted)? | Yes — relevance must be confirmed | **Agreed** |
| 5 | Auto-approve for `cited_by_count` increase and additive flag changes in v1? | Yes | **Open**** |
| 6 | All structural field changes go to human review in v1? | Yes | **Agreed** |
| 7 | History via staging audit log? | Yes | **Agreed** |
---

# Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Review queue grows faster than it is processed | Medium | Monitor queue depth per ingestion; escalation path if queue exceeds a defined threshold |
| Match key failure (record has neither ID nor DOI) | Low | Classified as `COMPARISON_UNRESOLVABLE`, surfaced separately for manual handling |
| EuropePMC changes API field names | Low | Diff field list is defined in code and versioned alongside the API client |
| Same article classified as NEW twice (concurrent ingestion runs) | Very low | Unique constraint on `id` in production prevents duplicate active records |
| Existing data has duplicate rows from prior ingestion bugs | Known | One-time migration sets `approved_by = 'system'` on the latest version per `id` |

---

# Next Steps

1. **Confirm remaining open questions** — needed before implementation begins
2. **Review and annotate this document** — add corrections or amendments before sharing
3. **Staging database setup** — schema via Liquibase, separate from production
4. **Auto-classify service** — comparison logic, known divergence matching, auto-approve rules
5. **Review API** — queue, approve, reject, export endpoints
6. **Promotion service** — staging → production write with audit logging
7. **Data migration** — set `approved_by / approved_at` on all existing production records

---

# Summary

| Today | After this change |
|---|---|
| All records inserted directly, no review | All records staged, classified, and curated before reaching the dashboard |
| Keyword match = record goes straight to dashboard | Keyword match = relevance reviewed by a human before promotion |
| No way to detect new vs. unchanged vs. changed records | Automatic per-record classification on every ingestion |
| No audit trail | Every action logged with who, when, and why — in both staging and production |
| No lineage | Full event history per article, queryable by PMID across both environments |
| Dashboard reflects raw API data | Dashboard reflects curated, human-approved data only |
| "How many new articles?" — unanswerable | Answered instantly from ingestion summary counts |
| "Who approved this article?" — unanswerable | Answered from `approved_by` on the production record and `REVIEW_APPROVED` in the audit log |

> [!IMPORTANT]
> The staging area is the foundation. Automation, bulk approval, downstream analytics, and compliance reporting all become possible once this layer is in place.

---

# Appendix — Glossary

| Term | Meaning |
|---|---|
| **Staging database** | Separate database where all EuropePMC records land first before any human review |
| **Production database** | The curated, approved store of records that drives the dashboard |
| **Ingested data** | Records pulled from the EuropePMC API and written to the staging database |
| **Auto-classify** | The automated step that categorises each staged record as NEW, UNCHANGED, or CHANGED |
| **Diff** | Field-by-field comparison between a staged record and its matching production record |
| **Review queue** | `pmc_review` table — records requiring a human approve or keep-existing decision |
| **Known divergence** | A recorded "keep existing" decision that suppresses re-surfacing of the same diff in future ingestions |
| **Auto-approve** | A low-risk change (metric field increase, additive flag) that is approved automatically without human review |
| **Promotion** | Writing an approved staging record to the production database |
| **Audit log** | `epmc_audit_log` — business event history in both staging and production, linked by `id` |
| **PMID** | PubMed ID — the primary stable identifier used to match records across ingestion runs |
| **Ingestion** | A single pull of records from the EuropePMC API |
| **Metric field** | A field that measures a count or availability state and is safe to auto-approve when it increases |
| **Structural field** | A field whose change may affect meaning or relevance — always requires human review |
