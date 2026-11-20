"""
Standalone script to backfill epmc_id in pmc_articles table.

Field mapping (API response → DB column):
  pmid   → pm_id      (already populated in DB)
  pmcid  → pmc_id     (already populated in DB)
  id     → epmc_id    (this is what we backfill)

Usage:
    DATABASE_URL=postgresql://user:pass@localhost:5432/dbname python scripts/backfill_epmc_id.py
    DATABASE_URL=postgresql://user:pass@localhost:5432/dbname python scripts/backfill_epmc_id.py --dry-run
"""

import argparse
import json
import os
import sys
import time

import psycopg2
import requests

EPMC_QUERY = (
    '(("GA4GH" OR "Global Alliance for Genomics and Health") '
    'NOT (PUB_TYPE:("published erratum")))'
)
EPMC_BASE_URL = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    "?query=%28%28%22GA4GH%22%20OR%20%22Global%20Alliance%20for%20Genomics%20and%20Health%22%29"
    "%20NOT%20%28PUB_TYPE%3A%28%22published%20erratum%22%29%29%29"
    "&format=json&resultType=core&pageSize=1000"
)


def fetch_all_articles():
    articles = []
    cursor = "*"
    page = 1
    hit_count = None

    while True:
        url = f"{EPMC_BASE_URL}&cursorMark={cursor}"

        if page == 1:
            print(f"Search query : {EPMC_QUERY}")
            print(f"API URL      : {url}\n")

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if hit_count is None:
            hit_count = data.get("hitCount", 0)
            print(f"Total results reported by EuropePMC (hitCount): {hit_count}\n")

        results = data.get("resultList", {}).get("result", [])
        articles.extend(results)

        next_cursor = data.get("nextCursorMark")
        print(f"  Page {page}: received {len(results)} articles  (running total: {len(articles)})")

        if not next_cursor or next_cursor == cursor or not results:
            break

        cursor = next_cursor
        page += 1
        time.sleep(0.5)

    print(f"\nFetched {len(articles)} articles from EuropePMC (hitCount={hit_count})")
    return articles, hit_count


def load_db_records(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, pm_id, pmc_id, epmc_id FROM pmc_articles ORDER BY id;")
    rows = cur.fetchall()
    cur.close()
    print(f"Records in DB (pmc_articles): {len(rows)}")
    return rows


def build_api_lookup(articles):
    """Build lookup maps keyed by each identifier present in the API response."""
    by_pmcid = {}  # API pmcid  → article record
    by_pmid = {}   # API pmid   → article record
    by_id = {}     # API id     → article record (covers preprints with no pmid/pmcid)

    for article in articles:
        epmc_id = article.get("id")
        pmid = article.get("pmid")
        pmcid = article.get("pmcid")

        if not epmc_id:
            continue

        record = {"epmc_id": epmc_id, "pmid": pmid, "pmcid": pmcid}
        by_id[epmc_id] = record
        if pmcid:
            by_pmcid[pmcid] = record
        if pmid:
            by_pmid[pmid] = record

    return by_pmcid, by_pmid, by_id


def compare_api_vs_db(articles, db_rows):
    """
    Report which API articles have no matching row in the DB.
    A DB row matches when its pm_id == API pmid OR its pmc_id == API pmcid.
    """
    db_pm_ids = {row[1] for row in db_rows if row[1]}
    db_pmc_ids = {row[2] for row in db_rows if row[2]}

    not_in_db = []
    for article in articles:
        pmid = article.get("pmid")
        pmcid = article.get("pmcid")
        epmc_id = article.get("id")
        title = (article.get("title") or "")[:100]

        in_db = (pmid and pmid in db_pm_ids) or (pmcid and pmcid in db_pmc_ids)
        if not in_db:
            not_in_db.append({
                "epmc_id": epmc_id,
                "pmid": pmid,
                "pmcid": pmcid,
                "title": title,
            })

    print(f"\n{'='*60}")
    print(f"API vs DB comparison")
    print(f"{'='*60}")
    print(f"  EuropePMC articles fetched : {len(articles)}")
    print(f"  DB rows (pmc_articles)     : {len(db_rows)}")
    print(f"  In API but NOT in DB       : {len(not_in_db)}")

    if not_in_db:
        print(f"\n  Articles present in EuropePMC but missing from DB:")
        for a in not_in_db:
            print(f"    epmc_id={a['epmc_id']}  pmid={a['pmid']}  pmcid={a['pmcid']}")
            if a["title"]:
                print(f"    title  : {a['title']}")

    return not_in_db


def match_article(pm_id, pmc_id, by_pmcid, by_pmid, by_id):
    """
    Try to find the API article that corresponds to this DB row.
    Matching order (most to least specific):

    1. pmc_id (DB) == pmcid (API)
    2. pm_id (DB) looks like a PMC ID → treat as pmcid
    3. pm_id (DB) == pmid (API)
    4. pm_id (DB) == id (API)  — preprints where PPR id is stored in pm_id
    """
    # 1. match by pmc_id
    if pmc_id:
        match = by_pmcid.get(pmc_id)
        if match:
            return match, "pmc_id → pmcid"

    # 2. pm_id contains a PMC-format ID, treat it as pmcid
    if pm_id and pm_id.startswith("PMC"):
        match = by_pmcid.get(pm_id)
        if match:
            return match, "pm_id(PMC) → pmcid"

    # 3. match by pm_id == pmid
    if pm_id:
        match = by_pmid.get(pm_id)
        if match:
            return match, "pm_id → pmid"

    # 4. match by pm_id == id (preprints)
    if pm_id:
        match = by_id.get(pm_id)
        if match:
            return match, "pm_id → id (preprint)"

    return None, None


def backfill(conn, db_rows, by_pmcid, by_pmid, by_id, dry_run=False):
    cur = conn.cursor()

    updated = 0
    already_set = 0
    unmatched = []

    for row_id, pm_id, pmc_id, existing_epmc_id in db_rows:
        if existing_epmc_id:
            already_set += 1
            continue

        # normalise empty strings to None
        pm_id = pm_id or None
        pmc_id = pmc_id or None

        matched, strategy = match_article(pm_id, pmc_id, by_pmcid, by_pmid, by_id)

        if matched:
            epmc_id = matched["epmc_id"]
            if not dry_run:
                cur.execute(
                    "UPDATE pmc_articles SET epmc_id = %s WHERE id = %s;",
                    (epmc_id, row_id),
                )
            updated += 1
        else:
            unmatched.append({"row_id": row_id, "pm_id": pm_id, "pmc_id": pmc_id})

    if not dry_run:
        conn.commit()

    print(f"\n{'='*60}")
    print(f"{'[DRY RUN] ' if dry_run else ''}Backfill results")
    print(f"{'='*60}")
    print(f"  Updated      : {updated}")
    print(f"  Already set  : {already_set}")
    print(f"  Unmatched    : {len(unmatched)}")

    if unmatched:
        print(f"\n  Unmatched rows (no epmc_id found):")
        for u in unmatched:
            print(f"    row_id={u['row_id']}  pm_id={u['pm_id']}  pmc_id={u['pmc_id']}")

    cur.close()
    return unmatched


def main():
    parser = argparse.ArgumentParser(
        description="Backfill epmc_id in pmc_articles from EuropePMC API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Match records and show results but do not write to the DB",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)

    print("=== EuropePMC epmc_id Backfill ===\n")
    if args.dry_run:
        print("DRY RUN — no changes will be written to the database\n")

    articles, hit_count = fetch_all_articles()
    by_pmcid, by_pmid, by_id = build_api_lookup(articles)

    print(f"\nConnecting to database...")
    conn = psycopg2.connect(database_url)

    try:
        db_rows = load_db_records(conn)
        not_in_db = compare_api_vs_db(articles, db_rows)

        print(f"\n{'='*60}")
        print("Backfilling epmc_id")
        print(f"{'='*60}")
        unmatched = backfill(conn, db_rows, by_pmcid, by_pmid, by_id, dry_run=args.dry_run)
    finally:
        conn.close()

    output_file = "scripts/match_result.json"
    with open(output_file, "w") as f:
        json.dump({"not_in_db": not_in_db, "unmatched": unmatched}, f, indent=2)
    print(f"\nResults saved to {output_file}")

    print("\nDone.")


if __name__ == "__main__":
    main()
