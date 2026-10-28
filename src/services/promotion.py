import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.models.entities.audit_log import AuditLog
from src.models.entities.enums import AuditEventType
from src.models.entities.pmc_article import PMCArticle
from src.models.entities.record import Record

logger = logging.getLogger(__name__)

# Fields from the diff that are safe to apply directly to a production article.
# Excludes PKs, FKs, and audit columns which are managed separately.
_DIFFABLE_FIELDS = {
    "source", "pmc_id", "doi", "title", "pub_year", "abstract_text",
    "affiliation", "publication_status", "language", "pub_type",
    "is_open_access", "inepmc", "inpmc", "has_pdf", "has_book",
    "has_suppl", "cited_by_count", "has_references", "date_of_creation",
    "first_index_date", "fulltext_receive_date", "revision_date",
    "epub_date", "first_publication_date",
}


@dataclass
class PromotionResult:
    ingestion_id: int
    promoted_new: int = 0
    promoted_changed: int = 0
    skipped: int = 0        # approved but review_type not new/changed
    errors: List[str] = field(default_factory=list)


class PromotionService:
    """
    Promotes approved staged records to the production database.

    NEW approved    → copy Record + PMCArticle to production, set approved_by/approved_at
    CHANGED approved → apply diff fields to existing production article, update approved_by/approved_at

    After each successful write:
      - staging audit log entry written (ARTICLE_PROMOTED / PRODUCTION_ARTICLE_UPDATED)
      - production audit log entry written (ARTICLE_PROMOTED / PRODUCTION_ARTICLE_UPDATED)
      - pmc_review row marked promoted in staging

    staging_repo   — reads reviews and staged articles; writes staging audit log
    production_repo — reads/writes production articles; writes production audit log
    """

    def __init__(self, staging_repo, production_repo) -> None:
        self.staging_repo = staging_repo
        self.production_repo = production_repo

    def promote(self, ingestion_id: int, promoted_by: str) -> PromotionResult:
        result = PromotionResult(ingestion_id=ingestion_id)
        now = datetime.now(timezone.utc)

        reviews = self.staging_repo.get_approved_reviews(ingestion_id)
        if not reviews:
            logger.info("PROMOTION no approved reviews found ingestion_id=%d", ingestion_id)
            return result

        logger.info(
            "PROMOTION starting ingestion_id=%d approved_count=%d promoted_by=%s",
            ingestion_id, len(reviews), promoted_by,
        )

        for review in reviews:
            try:
                if review.review_type == "new":
                    self._promote_new(review, promoted_by, now, result)
                elif review.review_type == "changed":
                    self._promote_changed(review, promoted_by, now, result)
                else:
                    result.skipped += 1
                    logger.warning(
                        "PROMOTION unknown review_type=%s review_id=%d — skipping",
                        review.review_type, review.id,
                    )
            except Exception as e:
                result.errors.append(f"review_id {review.id} (epmc_id={review.epmc_id}): {e}")
                logger.exception(
                    "PROMOTION error review_id=%d epmc_id=%s", review.id, review.epmc_id
                )

        if result.promoted_new + result.promoted_changed > 0:
            self.staging_repo.commit_to_db()
            self.production_repo.commit_to_db()

        logger.info(
            "PROMOTION complete ingestion_id=%d promoted_new=%d promoted_changed=%d "
            "skipped=%d errors=%d",
            ingestion_id, result.promoted_new, result.promoted_changed,
            result.skipped, len(result.errors),
        )
        return result

    # ------------------------------------------------------------------
    # NEW article promotion
    # ------------------------------------------------------------------

    def _promote_new(self, review, promoted_by: str, now: datetime, result: PromotionResult) -> None:
        staged = self.staging_repo.get_article_by_epmc_id(review.epmc_id)
        if staged is None:
            raise ValueError(f"Staged article not found for epmc_id={review.epmc_id}")

        # Copy the parent Record to production first to satisfy the FK
        staged_record = self.staging_repo.get_record_by_id(staged.record_id)
        if staged_record is None:
            raise ValueError(f"Staged record not found record_id={staged.record_id}")

        prod_record = Record(
            record_type=staged_record.record_type,
            source=staged_record.source,
            status=staged_record.status,
            keyword=staged_record.keyword,
            product_line=staged_record.product_line,
            created_by=promoted_by,
            updated_by=promoted_by,
        )
        prod_record_id = self.production_repo.insert_record(prod_record)

        prod_article = PMCArticle(
            record_id=prod_record_id,
            source=staged.source,
            pm_id=staged.pm_id,
            pmc_id=staged.pmc_id,
            epmc_id=staged.epmc_id,
            full_text_id=staged.full_text_id,
            doi=staged.doi,
            title=staged.title,
            pub_year=staged.pub_year,
            abstract_text=staged.abstract_text,
            affiliation=staged.affiliation,
            publication_status=staged.publication_status,
            language=staged.language,
            pub_type=staged.pub_type,
            is_open_access=staged.is_open_access,
            inepmc=staged.inepmc,
            inpmc=staged.inpmc,
            has_pdf=staged.has_pdf,
            has_book=staged.has_book,
            has_suppl=staged.has_suppl,
            cited_by_count=staged.cited_by_count,
            has_references=staged.has_references,
            date_of_creation=staged.date_of_creation,
            first_index_date=staged.first_index_date,
            fulltext_receive_date=staged.fulltext_receive_date,
            revision_date=staged.revision_date,
            epub_date=staged.epub_date,
            first_publication_date=staged.first_publication_date,
            approved_by=promoted_by,
            approved_at=now,
            created_by=promoted_by,
            created_at=now,
            updated_by=promoted_by,
            updated_at=now,
            version=1,
        )
        self.production_repo.insert_article(prod_article)

        self._write_audit(
            repo=self.staging_repo,
            event_type=AuditEventType.ARTICLE_PROMOTED,
            review=review,
            action_by=promoted_by,
            now=now,
            comment="new article promoted to production",
        )
        self._write_audit(
            repo=self.production_repo,
            event_type=AuditEventType.ARTICLE_PROMOTED,
            review=review,
            action_by=promoted_by,
            now=now,
            comment="new article inserted into production",
            is_production=True,
        )

        self.staging_repo.mark_review_promoted(review.id)
        result.promoted_new += 1
        logger.info(
            "PROMOTION_NEW epmc_id=%s review_id=%d promoted_by=%s",
            review.epmc_id, review.id, promoted_by,
        )

    # ------------------------------------------------------------------
    # CHANGED article promotion
    # ------------------------------------------------------------------

    def _promote_changed(self, review, promoted_by: str, now: datetime, result: PromotionResult) -> None:
        diff = review.diff or {}

        # Extract only the new values from the diff, restricted to safe fields
        update_fields = {
            field: change["new"]
            for field, change in diff.items()
            if field in _DIFFABLE_FIELDS
        }
        update_fields["approved_by"] = promoted_by
        update_fields["approved_at"] = now
        update_fields["updated_by"] = promoted_by
        update_fields["updated_at"] = now

        self.production_repo.update_article_fields(review.epmc_id, update_fields)

        self._write_audit(
            repo=self.staging_repo,
            event_type=AuditEventType.PRODUCTION_ARTICLE_UPDATED,
            review=review,
            action_by=promoted_by,
            now=now,
            comment=f"changed fields promoted: {', '.join(diff.keys())}",
        )
        self._write_audit(
            repo=self.production_repo,
            event_type=AuditEventType.PRODUCTION_ARTICLE_UPDATED,
            review=review,
            action_by=promoted_by,
            now=now,
            comment=f"fields updated from approved review: {', '.join(diff.keys())}",
            is_production=True,
        )

        self.staging_repo.mark_review_promoted(review.id)
        result.promoted_changed += 1
        logger.info(
            "PROMOTION_CHANGED epmc_id=%s review_id=%d fields=%s promoted_by=%s",
            review.epmc_id, review.id, list(diff.keys()), promoted_by,
        )

    # ------------------------------------------------------------------
    # Audit log helper
    # ------------------------------------------------------------------

    def _write_audit(self, repo, event_type, review, action_by: str, now: datetime, comment: str, is_production: bool = False) -> None:
        repo.insert_audit_log(AuditLog(
            event_type=event_type,
            entity_type="pmc_article",
            entity_id=str(review.staging_id),
            epmc_id=review.epmc_id,
            doi=review.doi,
            # ingestion_id is a staging entiry - not required in production
            ingestion_id=None if is_production else review.ingestion_id,
            new_value={"review_id": review.id, "promoted_by": action_by},
            comment=comment,
            action_by=action_by,
            action_at=now,
        ))
