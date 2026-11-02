from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PMCReview(Base):
    __tablename__ = "pmc_review"

    # ---------- PK ----------
    id: Mapped[int] = mapped_column(primary_key=True)

    # ---------- FK ----------
    ingestion_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion.id", ondelete="CASCADE"), nullable=False
    )
    staging_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pmc_articles.id", ondelete="NO ACTION")
    )

    # ---------- Identity ----------
    epmc_id: Mapped[Optional[str]] = mapped_column(String(64))
    doi: Mapped[Optional[str]] = mapped_column(String(128))

    # ---------- Classification ----------
    review_type: Mapped[str] = mapped_column(String(16), nullable=False)
    diff: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    # ---------- Auto-approve ----------
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_approve_reason: Mapped[Optional[str]] = mapped_column(Text)

    # ---------- Review ----------
    review_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    review_comment: Mapped[Optional[str]] = mapped_column(Text)

    # ---------- Audit ----------
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
