import io
import logging
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

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
    skipped_empty: int   # rows where Decision was blank
    invalid: List[str]   # human-readable reasons for rows that could not be parsed


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
