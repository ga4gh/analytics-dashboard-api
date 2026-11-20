#!/usr/bin/env python
"""
Backfill related tables for production articles that were promoted before
_copy_related_records existed (pmc_authors, articles_authors, pmc_affiliations,
citations, pmc_references, grants).

Scoped to a single staging ingestion run (defaults to the latest).  For each
staging article in that run the script finds the matching production article by
epmc_id, then copies all associated rows using the production PKs as FK targets —
the same logic as PromotionService._copy_related_records.

Idempotent: articles that already have articles_authors rows in production are
skipped, so the script is safe to re-run.

Usage (from repo root with pmc_venv activated):

  Dry run against the latest ingestion:
    python scripts/backfill_related_tables.py --dry-run

  Real run against the latest ingestion:
    python scripts/backfill_related_tables.py

  Target a specific ingestion ID:
    python scripts/backfill_related_tables.py --ingestion-id 25545

Required env vars:
  DATABASE_URL             — staging RDS connection string
  PRODUCTION_DATABASE_URL  — production RDS connection string
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, ".")

from src.models.entities.citations import Citation, Reference
from src.models.entities.extras import Grant
from src.models.entities.ingestion import Ingestion
from src.models.entities.pmc_article import PMCArticle
from src.models.entities.pmc_author import ArticleAuthor, PMCAffiliation, PMCAuthor
from src.repositories.epmc import EPMCRepo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PROMOTED_BY = "backfill_script"
COMMIT_EVERY = 50  # commit to production every N articles


def make_session(url: str):
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_recycle=300,  # recycle connections every 5 minutes to avoid RDS idle timeout
        connect_args={
            "connect_timeout": 30,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return Session()


def copy_related(staging_repo, prod_repo, staged_id, prod_article_id, staged_record_id, prod_record_id, now, dry_run):
    """
    Copy all related rows for one article from staging → production.
    Returns a dict with counts of rows written per table.
    """
    author_id_map: dict[int, int] = {}

    # 1. Authors + ArticleAuthor junction
    article_authors = staging_repo.get_article_authors_for_article(staged_id)
    for aa in article_authors:
        staging_author = staging_repo.get_author_by_id(aa.author_id)
        if staging_author is None:
            continue

        prod_author = PMCAuthor(
            fullname=staging_author.fullname,
            firstname=staging_author.firstname,
            lastname=staging_author.lastname,
            initials=staging_author.initials,
            orcid=staging_author.orcid,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        prod_aa = ArticleAuthor(
            article_id=prod_article_id,
            author_order=aa.author_order,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        if not dry_run:
            prod_author_id = prod_repo.insert_author(prod_author)
            prod_aa.author_id = prod_author_id
            prod_repo.insert_article_author(prod_aa)
        else:
            prod_author_id = -1
        author_id_map[aa.author_id] = prod_author_id

    # 2. Affiliations (need author_id mapping from step 1)
    affiliations = staging_repo.get_affiliations_for_article(staged_id)
    for aff in affiliations:
        prod_author_id = author_id_map.get(aff.author_id)
        if prod_author_id is None:
            continue
        prod_aff = PMCAffiliation(
            author_id=prod_author_id,
            article_id=prod_article_id,
            org_name=aff.org_name,
            affiliation_order=aff.affiliation_order,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        if not dry_run:
            prod_repo.insert_affiliation(prod_aff)

    # 3. Citations
    citations = staging_repo.get_citations_for_article(staged_id)
    for cit in citations:
        prod_cit = Citation(
            article_id=prod_article_id,
            citation_id=cit.citation_id,
            source=cit.source,
            citation_type=cit.citation_type,
            title=cit.title,
            authors=cit.authors,
            pub_year=cit.pub_year,
            citation_count=cit.citation_count,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        if not dry_run:
            prod_repo.insert_citation(prod_cit)

    # 4. References
    references = staging_repo.get_references_for_article(staged_id)
    for ref in references:
        prod_ref = Reference(
            article_id=prod_article_id,
            reference_id=ref.reference_id,
            source=ref.source,
            citation_type=ref.citation_type,
            title=ref.title,
            authors=ref.authors,
            pub_year=ref.pub_year,
            issn=ref.issn,
            essn=ref.essn,
            cited_order=ref.cited_order,
            match=ref.match,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        if not dry_run:
            prod_repo.insert_reference(prod_ref)

    # 5. Grants (linked to record, not article)
    grants = staging_repo.get_grants_for_record(staged_record_id)
    for g in grants:
        prod_grant = Grant(
            record_id=prod_record_id,
            grant_id=g.grant_id,
            agency=g.agency,
            family_name=g.family_name,
            given_name=g.given_name,
            initials=g.initials,
            alias=g.alias,
            orcid=g.orcid,
            funder_name=g.funder_name,
            doi=g.doi,
            title=g.title,
            abstract=g.abstract,
            start_date=g.start_date,
            end_date=g.end_date,
            institution_name=g.institution_name,
            ingestion_id=None,
            created_by=PROMOTED_BY,
            created_at=now,
            updated_by=PROMOTED_BY,
            updated_at=now,
            version=1,
        )
        if not dry_run:
            prod_repo.insert_grant(prod_grant)

    return {
        "authors": len(article_authors),
        "affiliations": len(affiliations),
        "citations": len(citations),
        "references": len(references),
        "grants": len(grants),
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill related tables for already-promoted production articles")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without touching the DB")
    parser.add_argument("--ingestion-id", type=int, default=None,
                        help="Staging ingestion ID to backfill (default: latest)")
    args = parser.parse_args()

    staging_url = os.environ.get("DATABASE_URL") or os.environ.get("STAGING_DB_URL")
    prod_url = os.environ.get("PRODUCTION_DATABASE_URL")

    if not staging_url:
        sys.exit("ERROR: set DATABASE_URL (staging RDS connection string)")
    if not prod_url:
        sys.exit("ERROR: set PRODUCTION_DATABASE_URL (production RDS connection string)")

    staging_session = make_session(staging_url)
    prod_session = make_session(prod_url)

    staging_repo = EPMCRepo(staging_session)
    prod_repo = EPMCRepo(prod_session)

    now = datetime.now(timezone.utc)

    # Resolve ingestion ID — default to latest in staging
    ingestion_id = args.ingestion_id
    if ingestion_id is None:
        ingestion_id = (
            staging_session.query(Ingestion.id)
            .order_by(Ingestion.id.desc())
            .limit(1)
            .scalar()
        )
        if ingestion_id is None:
            sys.exit("ERROR: no ingestion runs found in staging DB")
        logger.info("No --ingestion-id supplied; using latest: ingestion_id=%d", ingestion_id)
    else:
        logger.info("Using supplied ingestion_id=%d", ingestion_id)

    # Fetch all staging articles from that ingestion run
    staged_articles = (
        staging_session.query(PMCArticle)
        .filter(PMCArticle.ingestion_id == ingestion_id)
        .order_by(PMCArticle.id)
        .all()
    )
    total = len(staged_articles)
    if total == 0:
        sys.exit(f"ERROR: no pmc_articles found in staging for ingestion_id={ingestion_id}")
    logger.info("Staging articles in ingestion_id=%d: %d", ingestion_id, total)

    already_done = backfilled = skipped = errors = 0
    totals: dict[str, int] = {"authors": 0, "affiliations": 0, "citations": 0, "references": 0, "grants": 0}
    pending_commit = 0

    for i, staged in enumerate(staged_articles, 1):
        try:
            # Find this article in production by epmc_id
            prod_article = prod_repo.get_article_by_epmc_id(staged.epmc_id)
            if prod_article is None:
                logger.warning("[%d/%d] epmc_id=%s not found in production — skipping (not promoted yet?)",
                               i, total, staged.epmc_id)
                skipped += 1
                continue

            # Idempotency check: skip if articles_authors already has rows in production
            existing = prod_session.query(ArticleAuthor).filter(
                ArticleAuthor.article_id == prod_article.id
            ).count()
            if existing > 0:
                already_done += 1
                continue

            counts = copy_related(
                staging_repo, prod_repo,
                staged.id, prod_article.id,
                staged.record_id, prod_article.record_id,
                now, args.dry_run,
            )

            for k in totals:
                totals[k] += counts[k]

            backfilled += 1
            pending_commit += 1

            logger.info(
                "%s [%d/%d] epmc_id=%s authors=%d affiliations=%d citations=%d references=%d grants=%d",
                "[DRY RUN]" if args.dry_run else "BACKFILLED",
                i, total, staged.epmc_id,
                counts["authors"], counts["affiliations"],
                counts["citations"], counts["references"], counts["grants"],
            )

            # Commit in batches to avoid one giant transaction
            if not args.dry_run and pending_commit >= COMMIT_EVERY:
                prod_session.commit()
                logger.info("--- committed %d articles (running total: %d) ---", pending_commit, backfilled)
                pending_commit = 0

        except Exception as e:
            logger.exception("ERROR processing epmc_id=%s: %s", staged.epmc_id, e)
            if not args.dry_run:
                prod_session.rollback()
            pending_commit = 0
            errors += 1

    # Final commit for any remaining
    if not args.dry_run and pending_commit > 0:
        prod_session.commit()
        logger.info("--- final commit: %d articles ---", pending_commit)

    staging_session.close()
    prod_session.close()

    logger.info(
        "\n=== SUMMARY (ingestion_id=%d) ===\n"
        "  backfilled:   %d\n"
        "  already_done: %d\n"
        "  skipped:      %d\n"
        "  errors:       %d\n"
        "  rows written: authors=%d affiliations=%d citations=%d references=%d grants=%d",
        ingestion_id, backfilled, already_done, skipped, errors,
        totals["authors"], totals["affiliations"], totals["citations"],
        totals["references"], totals["grants"],
    )

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
