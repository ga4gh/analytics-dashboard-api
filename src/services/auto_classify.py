import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.models.entities.audit_log import AuditLog
from src.models.entities.enums import AuditEventType
from src.models.entities.pmc_article import PMCArticle
from src.models.entities.pmc_review import PMCReview
from src.repositories.epmc import EPMCRepo

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
    known_divergence_count: int = 0
    auto_approved_count: int = 0
    pending_review_count: int = 0
    unresolvable_count: int = 0


class AutoClassifyService:
    """
    Compares every article from a completed ingestion run against the production
    database and classifies each record as NEW, UNCHANGED, CHANGED, or
    KNOWN_DIVERGENCE.

    All DB reads/writes go through the repo layer — no raw session access.
    staging_repo  — reads staged articles and known divergences; writes reviews and audit logs.
    production_repo — reads curated production articles for comparison.
    """

    def __init__(self, staging_repo: EPMCRepo, production_repo: EPMCRepo) -> None:
        self.staging_repo = staging_repo
        self.production_repo = production_repo

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

        staged = self.staging_repo.get_staged_articles(ingestion_id)
        result.total_pulled = len(staged)

        for staged_article in staged:
            prod_article, match_key = self._find_in_production(staged_article)

            if match_key == "unresolvable":
                result.unresolvable_count += 1
                self._write_audit_log(
                    event_type=AuditEventType.ARTICLE_UNRESOLVABLE,
                    staged=staged_article,
                    ingestion_id=ingestion_id,
                    action_by=created_by,
                )
                logger.warning(
                    "CLASSIFICATION_UNRESOLVABLE ingestion_id=%d article.id=%d",
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
                self._write_audit_log(
                    event_type=AuditEventType.ARTICLE_CLASSIFIED_NEW,
                    staged=staged_article,
                    ingestion_id=ingestion_id,
                    action_by=created_by,
                    new_value={"title": staged_article.title, "epmc_id": staged_article.epmc_id},
                )
                logger.info(
                    "CLASSIFICATION_NEW epmc_id=%s ingestion_id=%d",
                    staged_article.epmc_id or staged_article.doi, ingestion_id,
                )

            else:
                # ---- UNCHANGED or CHANGED ------------------------------
                full_diff = self._compute_diff(prod_article, staged_article)

                if not full_diff:
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
                    self._write_audit_log(
                        event_type=AuditEventType.ARTICLE_CLASSIFIED_UNCHANGED,
                        staged=staged_article,
                        ingestion_id=ingestion_id,
                        action_by=created_by,
                    )
                    logger.info(
                        "CLASSIFICATION_UNCHANGED epmc_id=%s ingestion_id=%d",
                        staged_article.epmc_id or staged_article.doi, ingestion_id,
                    )
                else:
                    # Filter out fields covered by active known divergences
                    effective_diff = self._filter_known_divergences(
                        staged_article.epmc_id, staged_article.doi, full_diff
                    )

                    if not effective_diff:
                        # All changed fields are known divergences — suppress
                        result.changed_count += 1
                        result.known_divergence_count += 1
                        result.auto_approved_count += 1
                        self._write_review(
                            ingestion_id=ingestion_id,
                            staged=staged_article,
                            review_type="changed",
                            diff=full_diff,
                            auto_approved=True,
                            auto_approve_reason="known_divergences",
                            review_status="approved",
                            created_by=created_by,
                        )
                        self._write_audit_log(
                            event_type=AuditEventType.ARTICLE_CLASSIFIED_KNOWN_DIV,
                            staged=staged_article,
                            ingestion_id=ingestion_id,
                            action_by=created_by,
                            new_value={"suppressed_fields": list(full_diff.keys())},
                        )
                        logger.info(
                            "CLASSIFICATION_KNOWN_DIVERGENCE epmc_id=%s ingestion_id=%d fields=%s",
                            staged_article.epmc_id or staged_article.doi,
                            ingestion_id,
                            list(full_diff.keys()),
                        )
                    else:
                        # CHANGED — check auto-approve rules
                        result.changed_count += 1
                        auto_approved, approve_reason = self._check_auto_approve(effective_diff)

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
                            diff=effective_diff,
                            auto_approved=auto_approved,
                            auto_approve_reason=approve_reason,
                            review_status=review_status,
                            created_by=created_by,
                        )
                        self._write_audit_log(
                            event_type=AuditEventType.ARTICLE_CLASSIFIED_CHANGED,
                            staged=staged_article,
                            ingestion_id=ingestion_id,
                            action_by=created_by,
                            old_value={f: effective_diff[f]["old"] for f in effective_diff},
                            new_value={f: effective_diff[f]["new"] for f in effective_diff},
                            comment=f"auto_approved={auto_approved}",
                        )
                        logger.info(
                            "CLASSIFICATION_CHANGED epmc_id=%s ingestion_id=%d fields=%s auto_approved=%s",
                            staged_article.epmc_id or staged_article.doi,
                            ingestion_id,
                            list(effective_diff.keys()),
                            auto_approved,
                        )

        # Summary audit log for the full run
        self._write_audit_log(
            event_type=AuditEventType.INGESTION_CLASSIFICATION_COMPLETE,
            staged=None,
            ingestion_id=ingestion_id,
            action_by=created_by,
            new_value={
                "total_pulled": result.total_pulled,
                "new_count": result.new_count,
                "unchanged_count": result.unchanged_count,
                "changed_count": result.changed_count,
                "known_divergence_count": result.known_divergence_count,
                "auto_approved_count": result.auto_approved_count,
                "pending_review_count": result.pending_review_count,
                "unresolvable_count": result.unresolvable_count,
            },
        )

        # Write classification counts back to the ingestion row
        self.staging_repo.update_ingestion_counts(ingestion_id, {
            "total_pulled": result.total_pulled,
            "new_count": result.new_count,
            "unchanged_count": result.unchanged_count,
            "changed_count": result.changed_count,
            "auto_approved_count": result.auto_approved_count,
            "pending_review_count": result.pending_review_count,
            "unresolvable_count": result.unresolvable_count,
        })

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
    ) -> int:
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
        return self.staging_repo.insert_review(review)

    # ------------------------------------------------------------------
    # Audit log writer
    # ------------------------------------------------------------------

    def _write_audit_log(
        self,
        event_type: AuditEventType,
        staged: Optional[PMCArticle],
        ingestion_id: int,
        action_by: str = "system",
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        comment: Optional[str] = None,
    ) -> None:
        log = AuditLog(
            event_type=event_type,
            entity_type="pmc_article" if staged is not None else "ingestion",
            entity_id=str(staged.id) if staged is not None else str(ingestion_id),
            epmc_id=staged.epmc_id if staged is not None else None,
            doi=staged.doi if staged is not None else None,
            ingestion_id=ingestion_id,
            old_value=old_value,
            new_value=new_value,
            comment=comment,
            action_by=action_by,
            action_at=datetime.now(timezone.utc),
        )
        self.staging_repo.insert_audit_log(log)

    # ------------------------------------------------------------------
    # Known divergence filter
    # ------------------------------------------------------------------

    def _filter_known_divergences(
        self,
        epmc_id: Optional[str],
        doi: Optional[str],
        diff: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Remove fields from diff already covered by an active known_divergence.

        A field is suppressed when:
          - known_divergences has an active row for this article + field_path
          - epmc_value matches the incoming new value from EPMC

        If EPMC starts sending a different value the suppression lifts.
        """
        if not diff:
            return diff

        known = self.staging_repo.get_active_known_divergences(epmc_id, doi)
        if not known:
            return diff

        known_index = {kd.field_path: kd for kd in known}
        filtered: Dict[str, Any] = {}

        for field_name, change in diff.items():
            kd = known_index.get(field_name)
            if kd and str(change["new"]) == str(kd.epmc_value):
                logger.debug(
                    "KNOWN_DIVERGENCE_SUPPRESSED epmc_id=%s field=%s epmc_value=%s",
                    epmc_id or doi, field_name, kd.epmc_value,
                )
                continue
            filtered[field_name] = change

        return filtered

    # ------------------------------------------------------------------
    # Diff helpers
    # ------------------------------------------------------------------

    def _compute_diff(self, prod: PMCArticle, staged: PMCArticle) -> Dict[str, Any]:
        """
        Return {field: {"old": prod_value, "new": staged_value}} for changed fields.
        Empty dict means no differences.
        """
        diff: Dict[str, Any] = {}
        for field_name in DIFFABLE_FIELDS:
            old_val = getattr(prod, field_name, None)
            new_val = getattr(staged, field_name, None)
            if old_val != new_val:
                diff[field_name] = {"old": _serialise(old_val), "new": _serialise(new_val)}
        return diff

    def _check_auto_approve(self, diff: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Returns (auto_approved, reason_label).
        Every changed field must be covered by a passing rule.
        Empty rule list (v1) always returns (False, None).
        """
        if not AUTO_APPROVE_RULES:
            return False, None

        rule_index: Dict[str, AutoApproveRule] = {r.field: r for r in AUTO_APPROVE_RULES}
        matched_labels: List[str] = []

        for field_name, change in diff.items():
            rule = rule_index.get(field_name)
            if rule is None or not rule.applies(change["old"], change["new"]):
                return False, None
            matched_labels.append(rule.label)

        return True, ",".join(matched_labels)

    # ------------------------------------------------------------------
    # Match helpers
    # ------------------------------------------------------------------

    def _find_in_production(self, staged: PMCArticle) -> Tuple[Optional[PMCArticle], str]:
        """
        Match strategy:
          1. epmc_id  — primary stable identifier
          2. doi      — fallback
          3. Neither  → "unresolvable"

        Returns (article, match_key) where match_key is one of:
          "epmc_id", "doi", "new", "unresolvable"
        """
        if staged.epmc_id:
            prod = self.production_repo.get_article_by_epmc_id(staged.epmc_id)
            match_key = "epmc_id" if prod else "new"
            logger.info(
                "PRODUCTION_MATCH epmc_id=%s match_key=%s found=%s",
                staged.epmc_id, match_key, prod is not None,
            )
            return (prod, match_key)

        if staged.doi:
            prod = self.production_repo.get_article_by_doi(staged.doi)
            match_key = "doi" if prod else "new"
            logger.info(
                "PRODUCTION_MATCH doi=%s match_key=%s found=%s",
                staged.doi, match_key, prod is not None,
            )
            return (prod, match_key)

        logger.warning(
            "PRODUCTION_MATCH_UNRESOLVABLE staging_id=%s — no epmc_id or doi",
            staged.id,
        )
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
