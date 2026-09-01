from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # ---------- PK ----------
    id: Mapped[int] = mapped_column(primary_key=True)

    # ---------- Event ----------
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[Optional[str]] = mapped_column(String)
    entity_type: Mapped[Optional[str]] = mapped_column(String)
    entity_id: Mapped[Optional[str]] = mapped_column(String)

    # ---------- Identity ----------
    epmc_id: Mapped[Optional[str]] = mapped_column(String)
    doi: Mapped[Optional[str]] = mapped_column(String)

    # ---------- FK ----------
    ingestion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingestion.id", ondelete="NO ACTION")
    )
    review_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pmc_review.id", ondelete="NO ACTION")
    )

    # ---------- Values ----------
    old_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    new_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    comment: Mapped[Optional[str]] = mapped_column(Text)

    # ---------- Actor ----------
    action_by: Mapped[Optional[str]] = mapped_column(String)
    action_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
