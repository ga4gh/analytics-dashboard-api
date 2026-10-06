from enum import Enum


class AuditEventType(str, Enum):
    """
    Canonical event types written to the audit_log table.
    Covers the full lifecycle of a record through the curation pipeline.

    INGESTION
      INGESTION_STARTED                 — ingestion run begins (full or delta pull)
      INGESTION_COMPLETED               — all articles written to staging, counts updated
      INGESTION_FAILED                  — pipeline raised an unhandled exception

    CLASSIFICATION  (one per article per run)
      ARTICLE_CLASSIFIED_NEW            — no match in production (new record)
      ARTICLE_CLASSIFIED_UNCHANGED      — matched, diff is empty
      ARTICLE_CLASSIFIED_CHANGED        — matched, effective diff is non-empty
      ARTICLE_CLASSIFIED_KNOWN_DIV      — matched, all diff fields suppressed by known_divergences
      ARTICLE_UNRESOLVABLE              — no epmc_id or doi to match on
      INGESTION_CLASSIFICATION_COMPLETE — end of classify_ingestion_run(), carries count summary

    REVIEW  (human curator actions on pmc_review rows)
      REVIEW_APPROVED                   — curator accepted the incoming EPMC value
      REVIEW_REJECTED                   — curator kept the existing production value
      REVIEW_DEFERRED                   — curator postponed the decision

    KNOWN DIVERGENCE  (curator managing known_divergences table)
      KNOWN_DIVERGENCE_CREATED          — curator marked a field difference as a known divergence
      KNOWN_DIVERGENCE_DEACTIVATED      — known divergence retired (EPMC value now accepted)

    PROMOTION  (record lifecycle between staging and production)
      ARTICLE_PROMOTED                  — new article approved and written to production DB
      ARTICLE_PROMOTION_FAILED          — promotion attempt raised an error
      PRODUCTION_ARTICLE_UPDATED        — existing production record updated after approved CHANGED review
      PRODUCTION_UPDATE_FAILED          — production update attempt raised an error

    BASELINE
      BASELINE_MIGRATION_COMPLETE       — one-time backfill: existing records set approved_by='system'
    """

    # ---------- Ingestion lifecycle ----------
    INGESTION_STARTED = "INGESTION_STARTED"
    INGESTION_COMPLETED = "INGESTION_COMPLETED"
    INGESTION_FAILED = "INGESTION_FAILED"

    # ---------- Classification ----------
    ARTICLE_CLASSIFIED_NEW = "ARTICLE_CLASSIFIED_NEW"
    ARTICLE_CLASSIFIED_UNCHANGED = "ARTICLE_CLASSIFIED_UNCHANGED"
    ARTICLE_CLASSIFIED_CHANGED = "ARTICLE_CLASSIFIED_CHANGED"
    ARTICLE_CLASSIFIED_KNOWN_DIV = "ARTICLE_CLASSIFIED_KNOWN_DIV"
    ARTICLE_UNRESOLVABLE = "ARTICLE_UNRESOLVABLE"
    INGESTION_CLASSIFICATION_COMPLETE = "INGESTION_CLASSIFICATION_COMPLETE"

    # ---------- Human review actions ----------
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    REVIEW_DEFERRED = "REVIEW_DEFERRED"

    # ---------- Known divergence management ----------
    KNOWN_DIVERGENCE_CREATED = "KNOWN_DIVERGENCE_CREATED"
    KNOWN_DIVERGENCE_DEACTIVATED = "KNOWN_DIVERGENCE_DEACTIVATED"

    # ---------- Promotion ----------
    ARTICLE_PROMOTED = "ARTICLE_PROMOTED"
    ARTICLE_PROMOTION_FAILED = "ARTICLE_PROMOTION_FAILED"
    PRODUCTION_ARTICLE_UPDATED = "PRODUCTION_ARTICLE_UPDATED"
    PRODUCTION_UPDATE_FAILED = "PRODUCTION_UPDATE_FAILED"

    # ---------- Baseline ----------
    BASELINE_MIGRATION_COMPLETE = "BASELINE_MIGRATION_COMPLETE"
