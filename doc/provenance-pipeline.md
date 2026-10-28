# EPMC Data Provenance Pipeline

Step-by-step guide for running the EuropePMC data provenance workflow — from pulling articles through curator review to promoting approved records into the production database.
This documentation is created using Claude Code and and committed after manually reviewed.
## Table of Contents

- [Overview](#overview)
- [Pipeline at a Glance](#pipeline-at-a-glance)
- [Prerequisites](#prerequisites)
- [Step 1 — Ingest & Auto-Classify](#step-1--ingest--auto-classify)
- [Step 2 — Export the Review Queue](#step-2--export-the-review-queue)
- [Step 3 — Curator Review (Offline)](#step-3--curator-review-offline)
- [Step 4 — Import Review Decisions](#step-4--import-review-decisions)
- [Step 5 — Promote to Production](#step-5--promote-to-production)
- [Supporting Endpoints](#supporting-endpoints)
- [Review Status Reference](#review-status-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

The provenance pipeline ensures that every article in the production database has been pulled from EuropePMC, automatically classified for changes, reviewed by a curator, and explicitly approved before it reaches production. It runs in five sequential steps and uses two separate databases:

- **Staging DB** — receives all ingested and classified data; holds the review queue.
- **Production DB** — receives only approved, promoted records. Never written to directly during ingestion.

---

## Pipeline at a Glance

```
Europe PMC API
      │
      ▼
[Step 1] POST /epmc/ingest-pmc-data
      Pulls all keyword-matched articles → writes to staging
      Auto-classify runs immediately → populates pmc_review queue
      │
      ▼
[Step 2] GET /epmc/review/export
      Exports pending reviews to Excel/CSV
      File saved locally + optionally uploaded to S3
      │
      ▼
[Step 3] Curator fills Decision column (offline)
      approve / reject for each article row
      │
      ▼
[Step 4] POST /epmc/review/import
      Uploads completed file → applies decisions to staging
      Does NOT touch production DB
      │
      ▼
[Step 5] POST /epmc/review/promote
      Writes approved articles into production DB
      NEW → full insert; CHANGED → diff fields only
      Audit log written to both staging and production
```

---

## Prerequisites

- The API server running with both staging and production DB connections configured in `.env`
- `BASE_URL` set to the API base URL (e.g. `http://localhost:8000`)
- For S3 export upload: `EXPORT_S3_BUCKET` env var set

---

## Step 1 — Ingest & Auto-Classify

Pulls all GA4GH-related articles from EuropePMC and runs auto-classification in a single atomic call.

**What happens internally:**
1. **Phase 1 (delta)** — fetches only records updated since the last ingestion to build a set of changed `epmc_id`s (in-memory, not written to DB).
2. **Phase 2 (full pull)** — fetches all keyword-matched records and writes them to the staging `pmc_articles` table.
3. **Classification** — runs immediately; each staged article is compared against production and classified as `NEW`, `UNCHANGED`, `CHANGED`, or `UNRESOLVABLE`. Articles needing review are added to `pmc_review` with status `pending`.
4. A single commit writes articles + classification + review rows + audit logs atomically.

**Endpoint**

```
POST /epmc/ingest-pmc-data
Content-Type: application/json
```

**Request body**

| Parameter   | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `keyword`   | string | Yes      | Search term used to query EuropePMC — e.g. `"GA4GH"`. Must be consistent across all ingestion runs. |
| `from_date` | string | No       | Start of the delta window as `YYYY-MM-DD`. Defaults to the date of the last successful ingestion. |
| `to_date`   | string | No       | End of the delta window as `YYYY-MM-DD`. Defaults to today. |

**Example**

```bash
curl -X POST "$BASE_URL/epmc/ingest-pmc-data" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "GA4GH"}'
```

**Response** — `200 OK`

Returns the full list of articles now in the staging DB. The `ingestion_id` assigned to this run is recorded in server logs and discoverable via the export endpoint.

```json
[
  {
    "epmc_id": "PPR123456",
    "title": "GA4GH Data Connect specification...",
    "pub_year": 2024,
    "doi": "10.1093/bioinformatics/btad001",
    "is_open_access": true
  },
  ...
]
```

> **Tip:** Note the `ingestion_id` from the server logs. All downstream steps accept it as an optional parameter; if omitted each step auto-detects the latest run with pending/approved reviews.

---

## Step 2 — Export the Review Queue

Generates an Excel or CSV file containing all articles queued for human review. Each row shows article metadata and, for CHANGED articles, the old and new field values side by side.

**Endpoint**

```
GET /epmc/review/export
```

**Query parameters**

| Parameter      | Type    | Required | Default   | Description |
|----------------|---------|----------|-----------|-------------|
| `ingestion_id` | integer | No       | Latest    | Ingestion run to export. Defaults to the latest run with pending reviews. |
| `format`       | string  | No       | `"excel"` | Output format — `"excel"` or `"csv"`. Excel recommended for curators. |

**Example**

```bash
# Export latest pending reviews as Excel
curl "$BASE_URL/epmc/review/export?format=excel"

# Export a specific ingestion run as CSV
curl "$BASE_URL/epmc/review/export?ingestion_id=42&format=csv"
```

**Response** — `200 OK`

```json
{
  "status": "success",
  "message": "Export finished for ingestion_id: 42",
  "ingestion_id": 42,
  "ingested_at": "2026-10-06 14:16 UTC",
  "total_pending_reviews": 18,
  "new_articles": 12,
  "changed_articles": 6,
  "format": "excel",
  "filename": "review_queue_42.xlsx",
  "file_path": "/app/exports/review_queue_42.xlsx",
  "download_url": "https://s3.amazonaws.com/..."
}
```

`download_url` is present only when `EXPORT_S3_BUCKET` is configured. Download the file from `file_path` (local) or `download_url` (S3) and pass it to the curator.

**Error** — `404` if no pending reviews exist for the requested ingestion run.

---

## Step 3 — Curator Review (Offline)

The exported file is filled in by a human curator. This step happens outside the API.

**How to fill the file:**

- Open the exported Excel or CSV file.
- For each row, fill the **Decision** column:

| Decision value | Meaning |
|----------------|---------|
| `approve`      | Accept this article (NEW: insert into production; CHANGED: apply new field values). |
| `reject`       | Decline this article (NEW: exclude from production; CHANGED: keep existing production values). |
| *(empty)*      | Skip — the row stays `pending` and will appear in the next export. |

- Save the file and keep the original filename — it helps with traceability.

---

## Step 4 — Import Review Decisions

Uploads the completed review file. Each row with a `Decision` of `approve` or `reject` is applied to the corresponding `pmc_review` row in the staging DB. An audit log entry is written for every decision. **No changes are made to the production DB at this step.**

**Endpoint**

```
POST /epmc/review/import
Content-Type: multipart/form-data
```

**Query parameters**

| Parameter     | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `reviewed_by` | string | Yes      | Name or email of the curator. Written to the audit log. |

**Form data**

| Field  | Type | Required | Description |
|--------|------|----------|-------------|
| `file` | file | Yes      | The completed review file. Accepted: `.xlsx`, `.xls`, `.csv`. |

**Example**

```bash
curl -X POST "$BASE_URL/epmc/review/import?reviewed_by=jane@ga4gh.org" \
  -F "file=@review_queue_42.xlsx"
```

**Response** — `200 OK`

```json
{
  "status": "success",
  "message": "Import complete — 16 decision(s) applied",
  "reviewed_by": "jane@ga4gh.org",
  "filename": "review_queue_42.xlsx",
  "total_rows_in_file": 18,
  "skipped_empty_decision": 2,
  "processed": 16,
  "skipped_already_reviewed": 0,
  "not_found": 0,
  "invalid_rows": [],
  "errors": []
}
```

| Response field               | Meaning |
|------------------------------|---------|
| `processed`                  | Decisions applied this call. |
| `skipped_empty_decision`     | Rows with no Decision value — still `pending`. |
| `skipped_already_reviewed`   | Rows already decided in a prior import — not overwritten. |
| `not_found`                  | `epmc_id`s in the file that don't exist in staging. |
| `invalid_rows`               | Rows with unrecognised Decision values. |

> **Safe to re-upload:** Uploading the same file twice is harmless. Already-decided rows are counted under `skipped_already_reviewed` and left unchanged.

---

## Step 5 — Promote to Production

Writes all `approved` reviews into the production database. After this step the promotion workflow is complete.

**What happens:**
- **NEW approved** → a new `Record` and `PMCArticle` row are inserted into production.
- **CHANGED approved** → only the approved diff fields are applied to the existing production article.
- Audit log entries are written to **both** staging and production DBs.
- Each review row is marked `promoted` immediately after its write succeeds, preventing double-promotion.

**Endpoint**

```
POST /epmc/review/promote
```

**Query parameters**

| Parameter      | Type    | Required | Description |
|----------------|---------|----------|-------------|
| `promoted_by`  | string  | Yes      | Name or email of the person triggering promotion. Written to the production audit log and set as `approved_by` on each article. |
| `ingestion_id` | integer | No       | Ingestion run to promote. Defaults to the latest run with `approved` reviews. Returns `404` if none exist. |

**Example**

```bash
curl -X POST "$BASE_URL/epmc/review/promote?promoted_by=jane@ga4gh.org"

# Promote a specific ingestion run
curl -X POST "$BASE_URL/epmc/review/promote?promoted_by=jane@ga4gh.org&ingestion_id=42"
```

**Response** — `200 OK`

```json
{
  "status": "success",
  "message": "Promotion complete for ingestion_id: 42",
  "ingestion_id": 42,
  "promoted_by": "jane@ga4gh.org",
  "promoted_new": 10,
  "promoted_changed": 5,
  "skipped": 0,
  "errors": []
}
```

| Response field    | Meaning |
|-------------------|---------|
| `promoted_new`    | New articles inserted into production. |
| `promoted_changed`| Existing articles updated with approved diff fields. |
| `skipped`         | Reviews with an unexpected `review_type` — logged as warnings. |
| `errors`          | Per-article error messages for any articles that failed. A non-empty list means some articles were not promoted; others in the same run may have succeeded. |

**Error** — `404` if no approved reviews exist for the requested ingestion run.

---

## Supporting Endpoints

These can be run independently of the core pipeline at any time.

### Ingest Grants

```
POST /epmc/ingest-pmc-grants
Content-Type: application/json
```

Fetches grant funding data from EuropePMC for a given keyword and populates the `grants` table. Run after Step 1 or independently.

```bash
curl -X POST "$BASE_URL/epmc/ingest-pmc-grants" \
  -H "Content-Type: application/json" \
  -d '{"keyword": "GA4GH"}'
```

### Ingest References

```
POST /epmc/ingest-pmc-references?use_db_articles=true
```

Fetches citation references for all articles in the staging DB.

| Parameter        | Type    | Default | Description |
|------------------|---------|---------|-------------|
| `use_db_articles`| boolean | `true`  | `true` — fetch references only for articles already in the DB. `false` — fetch for all keyword matches from EuropePMC. |

```bash
curl -X POST "$BASE_URL/epmc/ingest-pmc-references?use_db_articles=true"
```

---

## Review Status Reference

| Status      | Set by           | Meaning |
|-------------|------------------|---------|
| `pending`   | Auto-classify    | Awaiting curator decision. |
| `approved`  | Import (Step 4)  | Curator accepted — ready to promote. |
| `rejected`  | Import (Step 4)  | Curator declined — excluded from production. |
| `promoted`  | Promote (Step 5) | Successfully written to production. |

---

## Troubleshooting

**`404` on export — "No pending reviews found"**  
All reviews for the latest ingestion have already been decided (approved/rejected/promoted) or no ingestion has been run yet. Run Step 1 first, or specify a different `ingestion_id`.

**`404` on promote — "No approved reviews found"**  
Step 4 has not been run yet for this ingestion, or all approved reviews were already promoted. Check the review statuses in staging by querying `pmc_review` where `ingestion_id = <id>`.

**`errors` list non-empty after promote**  
Each entry names the `review_id` and `epmc_id` that failed and the exception message. Other records in the same run that succeeded are already committed to production. Fix the root cause (usually a missing staged article or missing `record_id`) and re-run Step 5 — only the remaining `approved` rows will be processed.

**Import returns `invalid_rows`**  
The Decision column contains an unrecognised value. Only `approve` and `reject` (case-insensitive) are accepted. Correct the file and re-upload.

**Import returns `not_found` entries**  
The `epmc_id` in the file does not exist in the staging `pmc_review` table. This can happen if the file is from a different ingestion run than the one currently in staging.
