import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.entities.pmc_article import PMCArticle
from src.models.entities.pmc_review import PMCReview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto-approve rule contract
# ---------------------------------------------------------------------------

@dataclass
class AutoApproveRule:
    """
    Declares when a single-field change is safe to auto-approve.

    field   — exact pmc_articles column name this rule covers
    label   — short slug written to auto_approve_reason on the pmc_review row
    applies — predicate(old_value, new_value) -> bool
              return True  → change is safe, counts toward auto-approval
              return False → change needs human review

    A CHANGED record is auto-approved only when EVERY field in its diff
    is covered by a rule whose predicate returns True. One uncovered or
    failing field blocks auto-approval for the whole record.
    """
    field: str
    label: str
    applies: Callable[[Any, Any], bool]


# ---------------------------------------------------------------------------
# Active rules — empty for v1 / Phase 1.
#
# HOW TO ADD A RULE (no other code changes needed):
#   1. Uncomment one of the ready-made examples below, or write a new one.
#   2. Deploy. The next ingestion run picks it up automatically.
#   3. Monitor pmc_review rows where auto_approved=True to validate the rule.
#
# Candidate rules to enable once update patterns are confirmed:
#
#   AutoApproveRule(
#       field="cited_by_count",
#       label="citation_count_increase",
#       applies=lambda old, new: isinstance(old, int) and isinstance(new, int) and new >= old,
#   ),
#   AutoApproveRule(
#       field="revision_date",
#       label="revision_date_update",
#       applies=lambda old, new: new is not None,
#   ),
#   AutoApproveRule(
#       field="first_index_date",
#       label="first_index_date_update",
#       applies=lambda old, new: new is not None,
#   ),
#   AutoApproveRule(
#       field="publication_status",
#       label="publication_status_progression",
#       # safe direction: preprint / ahead-of-print moving to published
#       applies=lambda old, new: old in ("aheadofprint", "ppublish") and new == "ppublish",
#   ),
#   AutoApproveRule(
#       field="is_open_access",
#       label="open_access_gained",
#       applies=lambda old, new: old in (None, "N", "false") and new in ("Y", "true"),
#   ),
# ---------------------------------------------------------------------------
AUTO_APPROVE_RULES: List[AutoApproveRule] = []

# Fields compared between staging and production. Excludes PKs, FKs,
# audit columns, and curation columns (approved_by/approved_at).
DIFFABLE_FIELDS: List[str] = [
    "source",
    "pmc_id",
    "doi",
    "title",
    "pub_year",
    "abstract_text",
    "affiliation",
    "publication_status",
    "language",
    "pub_type",
    "is_open_access",
    "inepmc",
    "inpmc",
    "has_pdf",
    "has_book",
    "has_suppl",
    "cited_by_count",
    "has_references",
    "date_of_creation",
    "first_index_date",
    "fulltext_receive_date",
    "revision_date",
    "epub_date",
    "first_publication_date",
]


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
    Writes pmc_review rows to staging_db.
    Updates the ingestion row counts in staging_db at completion.
    """

    def __init__(self, staging_db: Session, production_db: Session) -> None:
        self.staging_db = staging_db
        self.production_db = production_db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def classify_ingestion_run(self, ingestion_id: int, created_by: str = "system") -> ClassifyResult:
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
                # ---- NEW -----------------------------------------------
                result.new_count += 1
                result.pending_review_count += 1
                self._write_review(
                    ingestion_id=ingestion_id,
                    staged=staged_article,
                    review_type="new",
                    diff=None,
                    auto_approved=False,
                    auto_approve_reason=None,
                    review_status="pending",
                    created_by=created_by,
                )
                logger.info(
                    "CLASSIFICATION_NEW epmc_id=%s ingestion_id=%d",
                    staged_article.epmc_id or staged_article.doi, ingestion_id,
                )
            else:
                # ---- UNCHANGED or CHANGED ------------------------------
                diff = self._compute_diff(prod_article, staged_article)

                if not diff:
                    # UNCHANGED
                    result.unchanged_count += 1
                    result.auto_approved_count += 1
                    self._write_review(
                        ingestion_id=ingestion_id,
                        staged=staged_article,
                        review_type="unchanged",
                        diff=None,
                        auto_approved=True,
                        auto_approve_reason="no_changes_detected",
                        review_status="approved",
                        created_by=created_by,
                    )
                    logger.debug(
                        "CLASSIFICATION_UNCHANGED epmc_id=%s ingestion_id=%d",
                        staged_article.epmc_id or staged_article.doi, ingestion_id,
                    )
                else:
                    # CHANGED — check auto-approve rules
                    result.changed_count += 1
                    auto_approved, approve_reason = self._check_auto_approve(diff)

                    if auto_approved:
                        result.auto_approved_count += 1
                        review_status = "approved"
                    else:
                        result.pending_review_count += 1
                        review_status = "pending"

                    self._write_review(
                        ingestion_id=ingestion_id,
                        staged=staged_article,
                        review_type="changed",
                        diff=diff,
                        auto_approved=auto_approved,
                        auto_approve_reason=approve_reason,
                        review_status=review_status,
                        created_by=created_by,
                    )
                    logger.info(
                        "CLASSIFICATION_CHANGED epmc_id=%s ingestion_id=%d fields=%s auto_approved=%s",
                        staged_article.epmc_id or staged_article.doi,
                        ingestion_id,
                        list(diff.keys()),
                        auto_approved,
                    )

        self.staging_db.flush()

        # TODO Step 5: audit log events
        # TODO Step 6: write ingestion counts

        logger.info(
            "AutoClassifyService: classification complete ingestion_id=%d result=%s",
            ingestion_id,
            result,
        )
        return result

    # ------------------------------------------------------------------
    # Review writer
    # ------------------------------------------------------------------

    def _write_review(
        self,
        ingestion_id: int,
        staged: PMCArticle,
        review_type: str,
        diff: Optional[Dict[str, Any]],
        auto_approved: bool,
        auto_approve_reason: Optional[str],
        review_status: str,
        created_by: str,
    ) -> None:
        review = PMCReview(
            ingestion_id=ingestion_id,
            staging_id=staged.id,
            epmc_id=staged.epmc_id,
            doi=staged.doi or None,
            review_type=review_type,
            diff=diff,
            auto_approved=auto_approved,
            auto_approve_reason=auto_approve_reason,
            review_status=review_status,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        self.staging_db.add(review)

    # ------------------------------------------------------------------
    # Diff helpers
    # ------------------------------------------------------------------

    def _compute_diff(
        self, prod: PMCArticle, staged: PMCArticle
    ) -> Dict[str, Any]:
        """
        Return a dict of fields that differ between prod and staged.
        Format: {field: {"old": <prod_value>, "new": <staged_value>}}
        Empty dict means no differences.
        """
        diff: Dict[str, Any] = {}
        for field in DIFFABLE_FIELDS:
            old_val = getattr(prod, field, None)
            new_val = getattr(staged, field, None)
            if old_val != new_val:
                diff[field] = {"old": _serialise(old_val), "new": _serialise(new_val)}
        return diff

    def _check_auto_approve(
        self, diff: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns (auto_approved, reason_label).
        A diff is auto-approved only when EVERY changed field is covered by
        a rule whose predicate returns True.
        With an empty rule list (v1) this always returns (False, None).
        """
        if not AUTO_APPROVE_RULES:
            return False, None

        rule_index: Dict[str, AutoApproveRule] = {r.field: r for r in AUTO_APPROVE_RULES}
        matched_labels: List[str] = []

        for field, change in diff.items():
            rule = rule_index.get(field)
            if rule is None or not rule.applies(change["old"], change["new"]):
                return False, None
            matched_labels.append(rule.label)

        return True, ",".join(matched_labels)

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
          3. Neither present → (None, "unresolvable")

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


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _serialise(value: Any) -> Any:
    """Convert non-JSON-serialisable types before storing in JSONB diff."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value
    return str(value)
