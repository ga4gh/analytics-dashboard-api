from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class KnownDivergence(Base):
    __tablename__ = "known_divergences"

    # ---------- PK ----------
    id: Mapped[int] = mapped_column(primary_key=True)

    # ---------- FK ----------
    ingestion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingestion.id", ondelete="CASCADE")
    )
    review_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pmc_review.id", ondelete="CASCADE")
    )

    # ---------- Identity ----------
    epmc_id: Mapped[Optional[str]] = mapped_column(String(64))
    doi: Mapped[Optional[str]] = mapped_column(String(128))

    # ---------- Divergence detail ----------
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    epmc_value: Mapped[Optional[str]] = mapped_column(Text)
    retained_value: Mapped[Optional[str]] = mapped_column(Text)

    # ---------- State ----------
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---------- Rejection ----------
    rejected_by: Mapped[Optional[str]] = mapped_column(String(64))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    review_comment: Mapped[Optional[str]] = mapped_column(Text)

    # ---------- Audit ----------
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
