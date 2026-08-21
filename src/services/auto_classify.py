import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.entities.pmc_article import PMCArticle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Auto-approve rules
#
# Each rule is a dict with:
#   field   — the pmc_articles column name this rule applies to
#   label   — short human-readable name logged in auto_approve_reason
#   applies — callable(old_value, new_value) -> bool
#              returns True when the change is safe to auto-approve
#
# Leave this list empty for v1. Add rules here as patterns emerge from
# real ingestion runs — no structural code changes needed to add one.
#
# Example (do not activate until confirmed with stakeholders):
#   {
#       "field": "cited_by_count",
#       "label": "citation_count_increase",
#       "applies": lambda old, new: isinstance(new, int) and isinstance(old, int) and new > old,
#   }
# ---------------------------------------------------------------------------
AUTO_APPROVE_RULES: List[Dict[str, Any]] = []


@dataclass
class ClassifyResult:
    ingestion_id: int
    total_pulled: int = 0
    new_count: int = 0
    unchanged_count: int = 0
    changed_count: int = 0
    auto_approved_count: int = 0
    pending_review_count: int = 0
    unresolvable_count: int = 0


class AutoClassifyService:
    """
    Compares every article from a completed ingestion run against the production
    database and classifies each record as NEW, UNCHANGED, or CHANGED.

    Reads from staging_db (ingestion snapshot).
    Reads from production_db (current curated state).
    Writes pmc_review rows and audit_log events to staging_db.
    Updates the ingestion row counts in staging_db at completion.
    """

    def __init__(self, staging_db: Session, production_db: Session) -> None:
        self.staging_db = staging_db
        self.production_db = production_db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def classify_ingestion_run(self, ingestion_id: int) -> ClassifyResult:
        """
        Entry point. Classifies all articles written in this ingestion run.
        Returns a ClassifyResult with per-category counts.
        """
        result = ClassifyResult(ingestion_id=ingestion_id)
        logger.info("AutoClassifyService: starting classification for ingestion_id=%d", ingestion_id)

        staged = self._load_staged_articles(ingestion_id)
        result.total_pulled = len(staged)

        for staged_article in staged:
            prod_article, match_key = self._find_in_production(staged_article)

            if match_key == "unresolvable":
                result.unresolvable_count += 1
                logger.warning(
                    "COMPARISON_UNRESOLVABLE ingestion_id=%d article.id=%d",
                    ingestion_id, staged_article.id,
                )
                continue

            if prod_article is None:
                result.new_count += 1
                logger.info(
                    "COMPARISON_NEW epmc_id=%s ingestion_id=%d",
                    staged_article.epmc_id or staged_article.doi, ingestion_id,
                )
                # TODO Step 4: write pmc_review row for NEW
            else:
                # TODO Step 4: compute diff, route UNCHANGED / CHANGED
                pass

        # TODO Step 5: audit log events
        # TODO Step 6: write ingestion counts

        logger.info(
            "AutoClassifyService: classification complete ingestion_id=%d result=%s",
            ingestion_id,
            result,
        )
        return result

    # ------------------------------------------------------------------
    # Match helpers
    # ------------------------------------------------------------------

    def _load_staged_articles(self, ingestion_id: int) -> List[PMCArticle]:
        """Return all pmc_articles rows written in this ingestion run."""
        return (
            self.staging_db.execute(
                select(PMCArticle).where(PMCArticle.ingestion_id == ingestion_id)
            )
            .scalars()
            .all()
        )

    def _find_in_production(
        self, staged: PMCArticle
    ) -> Tuple[Optional[PMCArticle], str]:
        """
        Look up the staged article in the production DB.

        Match strategy:
          1. epmc_id (primary — stable EPMC identifier)
          2. doi     (fallback — used when epmc_id absent)
          3. Neither present → ("unresolvable", "unresolvable")

        Returns:
          (production_article, match_key) where match_key is one of:
            "epmc_id"       — matched on epmc_id
            "doi"           — matched on doi
            "new"           — no match found (record is new to production)
            "unresolvable"  — neither epmc_id nor doi present on staged article
        """
        if staged.epmc_id:
            prod = self.production_db.execute(
                select(PMCArticle).where(PMCArticle.epmc_id == staged.epmc_id)
            ).scalar_one_or_none()
            return (prod, "epmc_id" if prod else "new")

        if staged.doi:
            prod = self.production_db.execute(
                select(PMCArticle).where(PMCArticle.doi == staged.doi)
            ).scalar_one_or_none()
            return (prod, "doi" if prod else "new")

        return (None, "unresolvable")
