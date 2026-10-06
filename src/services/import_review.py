import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from src.models.entities.audit_log import AuditLog
from src.models.entities.enums import AuditEventType

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"approve", "reject"}


@dataclass
class ParsedReviewRow:
    review_id: int
    decision: str        # "approve" or "reject"
    comment: Optional[str]


@dataclass
class ParseResult:
    rows: List[ParsedReviewRow]
    skipped_empty: int       # rows where Decision was blank
    invalid: List[str]       # human-readable reasons for rows that could not be parsed


@dataclass
class ImportResult:
    processed: int = 0       # decisions successfully applied
    skipped: int = 0         # rows already reviewed (not pending)
    not_found: int = 0       # review_id not in DB
    errors: List[str] = field(default_factory=list)


def parse_review_file(content: bytes, filename: str) -> ParseResult:
    """
    Read a returned review Excel or CSV file and extract decisions.

    Only three columns are read: review_id, Decision, Comment.
    All other columns are ignored.

    Returns a ParseResult with valid rows, count of skipped empty-decision rows,
    and a list of strings describing any invalid rows.
    """
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(content), sheet_name="Review Queue", dtype=str)
    except Exception as e:
        raise ValueError(f"Could not read file '{filename}': {e}")

    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in ("review_id", "Decision") if c not in df.columns]
    if missing:
        raise ValueError(f"Required column(s) missing from file: {', '.join(missing)}")

    rows: List[ParsedReviewRow] = []
    skipped_empty = 0
    invalid: List[str] = []

    for idx, row in df.iterrows():
        line = idx + 2  # +2: 1-indexed + header row

        raw_decision = str(row.get("Decision", "") or "").strip()
        if not raw_decision:
            skipped_empty += 1
            continue

        decision = raw_decision.lower()
        if decision not in VALID_DECISIONS:
            invalid.append(f"Row {line}: invalid Decision '{raw_decision}' — must be approve or reject")
            continue

        raw_id = str(row.get("review_id", "") or "").strip()
        if not raw_id or raw_id in ("nan", ""):
            invalid.append(f"Row {line}: missing review_id")
            continue

        try:
            review_id = int(float(raw_id))
        except ValueError:
            invalid.append(f"Row {line}: review_id '{raw_id}' is not a valid integer")
            continue

        comment_raw = row.get("Comment", None)
        comment = str(comment_raw).strip() if comment_raw and str(comment_raw).strip() not in ("", "nan") else None

        rows.append(ParsedReviewRow(review_id=review_id, decision=decision, comment=comment))

    logger.info(
        "IMPORT parse complete file=%s valid=%d skipped_empty=%d invalid=%d",
        filename, len(rows), skipped_empty, len(invalid),
    )
    return ParseResult(rows=rows, skipped_empty=skipped_empty, invalid=invalid)


def apply_review_decisions(
    parsed: ParseResult,
    staging_repo,
    reviewed_by: str,
) -> ImportResult:
    """
    Apply parsed decisions to pmc_review rows in the staging DB.

    For each valid parsed row:
      - review_id not found          → counted as not_found, skipped
      - review already not pending   → counted as skipped
      - pending + valid decision     → update review_status, write audit log
    """
    result = ImportResult()
    now = datetime.now(timezone.utc)

    for row in parsed.rows:
        try:
            review = staging_repo.get_review_by_id(row.review_id)

            if review is None:
                result.not_found += 1
                logger.warning("IMPORT review_id=%d not found — skipping", row.review_id)
                continue

            if review.review_status != "pending":
                result.skipped += 1
                logger.info(
                    "IMPORT review_id=%d already %s — skipping",
                    row.review_id, review.review_status,
                )
                continue

            new_status = "approved" if row.decision == "approve" else "rejected"
            staging_repo.update_review(row.review_id, {
                "review_status": new_status,
                "reviewed_by": reviewed_by,
                "reviewed_at": now,
                "review_comment": row.comment,
            })

            event_type = (
                AuditEventType.REVIEW_APPROVED
                if new_status == "approved"
                else AuditEventType.REVIEW_REJECTED
            )
            staging_repo.insert_audit_log(AuditLog(
                event_type=event_type,
                entity_type="pmc_review",
                entity_id=str(review.id),
                epmc_id=review.epmc_id,
                doi=review.doi,
                ingestion_id=review.ingestion_id,
                new_value={"review_status": new_status, "reviewed_by": reviewed_by},
                comment=row.comment,
                action_by=reviewed_by,
                action_at=now,
            ))

            result.processed += 1
            logger.info(
                "IMPORT review_id=%d epmc_id=%s decision=%s reviewed_by=%s",
                row.review_id, review.epmc_id, new_status, reviewed_by,
            )

        except Exception as e:
            result.errors.append(f"review_id {row.review_id}: {e}")
            logger.exception("IMPORT error processing review_id=%d", row.review_id)

    if result.processed > 0:
        staging_repo.commit_to_db()

    logger.info(
        "IMPORT apply complete processed=%d skipped=%d not_found=%d errors=%d",
        result.processed, result.skipped, result.not_found, len(result.errors),
    )
    return result
