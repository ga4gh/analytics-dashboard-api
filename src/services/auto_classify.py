import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

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

    def classify_ingestion_run(self, ingestion_id: int) -> ClassifyResult:
        """
        Entry point. Classifies all articles written in this ingestion run.
        Returns a ClassifyResult with per-category counts.
        """
        result = ClassifyResult(ingestion_id=ingestion_id)
        logger.info("AutoClassifyService: starting classification for ingestion_id=%d", ingestion_id)

        # TODO Step 3: load staged articles for this ingestion_id
        # TODO Step 3: for each article, match against production
        # TODO Step 4: route to NEW / UNCHANGED / CHANGED branch
        # TODO Step 5: known divergence check + audit log events
        # TODO Step 6: write ingestion counts

        logger.info(
            "AutoClassifyService: classification complete ingestion_id=%d result=%s",
            ingestion_id,
            result,
        )
        return result
