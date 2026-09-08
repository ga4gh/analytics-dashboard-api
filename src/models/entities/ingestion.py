from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Ingestion(Base):
    __tablename__ = "ingestion"

    # ---------- PK ----------
    id: Mapped[int] = mapped_column(primary_key=True)

    # ---------- Core fields ----------
    ingested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    rows_count: Mapped[Optional[int]] = mapped_column(Integer)
    keyword: Mapped[Optional[str]] = mapped_column(String)
    api_version: Mapped[Optional[str]] = mapped_column(String)

    # ---------- Run type ----------
    run_type: Mapped[Optional[str]] = mapped_column(String(10), default="full")

    # ---------- Classification counts (written at INGESTION_COMPLETED) ----------
    total_pulled: Mapped[Optional[int]] = mapped_column(Integer)
    new_count: Mapped[Optional[int]] = mapped_column(Integer)
    unchanged_count: Mapped[Optional[int]] = mapped_column(Integer)
    changed_count: Mapped[Optional[int]] = mapped_column(Integer)
    auto_approved_count: Mapped[Optional[int]] = mapped_column(Integer)
    pending_review_count: Mapped[Optional[int]] = mapped_column(Integer)
    unresolvable_count: Mapped[Optional[int]] = mapped_column(Integer)

    # ---------- Audit ----------
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
