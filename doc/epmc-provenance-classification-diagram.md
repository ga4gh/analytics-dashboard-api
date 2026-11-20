# EPMC Data Provenance & Classification — Current Architecture

**Updated:** September 2026  
**Status:** Reflects implemented system (v1)

---

## Ingestion Pipeline — Two-Phase Pull

```
  Europe PMC API
       │
       │  Phase 1 — Delta Pull (in-memory, not written to DB)
       │  Fetches only records updated since last ingestion
       │  Produces: delta_epmc_ids (set of changed article IDs)
       │
       │  Phase 2 — Full Pull (written to staging DB)
       │  Fetches all keyword-matched records and writes to pmc_articles (staging)
       │  Writes: ingestion row with timestamp, keyword, total_pulled
       │
       ▼
  ┌─────────────────────────────────┐
  │     STAGING DATABASE            │
  │     pmc_articles (staged)       │
  └─────────────────────────────────┘
       │
       ▼
  Auto-Classify Service
  (runs immediately after Phase 2 completes)
```

---

## Classification Logic

```
  For each staged article
         │
         ▼
  Has epmc_id or doi?
         │
     No ─┴─ Yes
     │         │
     ▼         ▼
  UNRESOLVABLE  Lookup in PRODUCTION DB
  (audit log,   (epmc_id first, doi fallback)
   no review)          │
                 ┌─────┴─────┐
             Not found    Found
                 │            │
                 ▼            │
               NEW            │
          → pmc_review        │
            (pending)         │
                         Is epmc_id in delta_epmc_ids?
                              │
                    No ───────┴────── Yes
                    │                  │
                    ▼                  ▼
                 SKIPPED         Compute field diff
           (in production,      (DIFFABLE_FIELDS list)
            not updated —              │
            no action,          ┌──────┴──────┐
            no review)       No diff       Diff found
                                │              │
                                ▼              ▼
                           UNCHANGED    Filter known divergences
                          (audit log    (active rows in
                           only)         known_divergences table)
                                               │
                                  ┌────────────┴────────────┐
                            All fields                 Remaining diff
                            suppressed                     │
                                  │                        ▼
                                  ▼               Check auto-approve rules
                          CHANGED                 (v1: rules list is empty)
                          (auto_approved=True              │
                           reason: known_divergences)  ┌───┴───┐
                                               Rules match   No match
                                                   │              │
                                                   ▼              ▼
                                             CHANGED          CHANGED
                                             (auto_approved   (auto_approved=False
                                              =True)           review_status=pending)
                                                               → pmc_review queue
```

---

## Review Queue — What Reaches Human Review

| Classification | Goes to review queue? | Notes |
|---|---|---|
| NEW | Yes — `pending` | Relevance must be confirmed by curator |
| UNCHANGED | No | Audit log entry only |
| CHANGED — known divergence | No | Auto-approved, suppressed silently |
| CHANGED — auto-approve rules | No (v1: never, rules empty) | Auto-approved when rules match all diff fields |
| CHANGED — structural | Yes — `pending` | All changed fields require human decision |
| SKIPPED | No | Not in delta window — not updated |
| UNRESOLVABLE | No | Flagged in audit log for manual handling |

---

## Curator Review — Approve or Keep Existing

```
  Review queue (pmc_review, review_status = pending)
         │
         ▼
  Curator sees:
    - Article metadata (title, DOI, epmc_id, pub_year)
    - review_type: NEW or CHANGED
    - Full field diff: field → { old: "...", new: "..." }
    - auto_approve_reason (if partially auto-approved)
         │
         │
    ┌────┴────┐
  Approve   Keep existing
    │              │
    ▼              ▼
  PROMOTE      Record "known divergence"
  to           (field_path + epmc_value stored
  PRODUCTION   in known_divergences table,
  DB           active = TRUE)
               On next ingestion, same diff
               → suppressed automatically
```

---

## Known Divergence Lifecycle

```
  Ingestion N   — EPMC changes abstract
                  → CHANGED → curator: "Keep Existing"
                  → known_divergences: field=abstract_text, epmc_value="X", active=TRUE

  Ingestion N+1 — EPMC returns same abstract "X"
                  → diff detected
                  → matches known_divergence → SUPPRESSED (no review)

  Ingestion N+2 — EPMC changes abstract to "Y" (different value)
                  → diff detected
                  → does NOT match known_divergence (different epmc_value)
                  → known_divergence marked active=FALSE
                  → new diff queued for human review
```

---

## Key Tables (Staging DB)

| Table | Purpose |
|---|---|
| `pmc_articles` | Staged records from EuropePMC API |
| `ingestion` | One row per ingestion run — counts (new/unchanged/changed/skipped/pending) |
| `pmc_review` | Review queue — one row per article needing human decision |
| `known_divergences` | Active "keep existing" decisions — suppresses re-surfacing of same diff |
| `audit_log` | Full event history — every classification, review decision, and ingestion lifecycle event |

---

## What Changed from Original Design

| Original plan | Current implementation |
|---|---|
| Single-phase pull (all records) | Two-phase: delta pull (in-memory) + full pull (DB write) |
| 3 outcomes: NEW / UNCHANGED / CHANGED | 4 outcomes: NEW / UNCHANGED / CHANGED / **SKIPPED** |
| Known divergence as a manual step | Known divergence filter runs automatically in classify service |
| Auto-approve for metric fields (cited_by_count, flags) | Auto-approve framework built, rules **empty in v1** — all changes go to review |
| No export | Excel/CSV export of pending review queue with diff detail and Decision column |
