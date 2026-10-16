from datetime import datetime
from typing import List, Optional

from src.models.entities.citations import Citation, Reference
from src.models.entities.extras import FullText, Grant
from src.models.entities.pmc_author import PMCAffiliation, PMCAuthor, ArticleAuthor
from sqlalchemy import ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .pmc_author import PMCAffiliation, ArticleAuthor
from .extras import Grant, FullText
from .citations import Citation, Reference

class PMCArticle(Base):
    __tablename__ = "pmc_articles"

    # ---------- PK / FK ----------
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingestion.id", ondelete="SET NULL"),
    )

    # ---------- Core fields ----------
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    pm_id: Mapped[Optional[str]] = mapped_column(String(64))
    pmc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    full_text_id: Mapped[str] = mapped_column(String(128), nullable=False)
    doi: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    pub_year: Mapped[int] = mapped_column(Integer, nullable=False)
    abstract_text: Mapped[str] = mapped_column(Text, nullable=False)
    affiliation: Mapped[str] = mapped_column(Text, nullable=False)
    publication_status: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    pub_type: Mapped[Optional[List[str]]] = mapped_column(JSONB)

    # ---------- Flags ----------
    is_open_access: Mapped[str] = mapped_column(String(8), default=False)
    inepmc: Mapped[str] = mapped_column(String(8), default=False)
    inpmc: Mapped[str] = mapped_column(String(8), default=False)
    has_pdf: Mapped[str] = mapped_column(String(8), default=False)
    has_book: Mapped[str] = mapped_column(String(8), default=False)
    has_suppl: Mapped[str] = mapped_column(String(8), default=False)

    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    has_references: Mapped[str] = mapped_column(String(8), default=False)

    # ---------- Dates ----------
    date_of_creation: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    first_index_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    fulltext_receive_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    revision_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    epub_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    first_publication_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )

    # ---------- Audit ----------
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    deleted_by: Mapped[Optional[str]] = mapped_column(String(64))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True)
    )

    version: Mapped[int] = mapped_column(Integer, default=1)

    # ---------- Curation ----------
    epmc_id: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    # ---------- Relationships ----------
    article_authors: Mapped[List["ArticleAuthor"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ArticleAuthor.author_order"
    )

    affiliations: Mapped[List["PMCAffiliation"]] = relationship(
        cascade="all, delete-orphan",
        order_by="PMCAffiliation.affiliation_order"
    )

    fulltexts: Mapped[List["FullText"]] = relationship(
        cascade="all, delete-orphan"
    )

    citations: Mapped[List["Citation"]] = relationship(
        cascade="all, delete-orphan"
    )

    references: Mapped[List["Reference"]] = relationship(
        cascade="all, delete-orphan"
    )

class PMCArticleFull(PMCArticle):

    authors: Mapped[List["PMCAuthor"]] = relationship(
        "PMCAuthor",
        secondary="articles_authors",
        primaryjoin="PMCArticle.id == ArticleAuthor.article_id",
        secondaryjoin="PMCAuthor.id == ArticleAuthor.author_id",
        viewonly=True,
    )

    affiliations: Mapped[List["PMCAffiliation"]] = relationship(
        "PMCAffiliation",
        primaryjoin="PMCArticle.id == PMCAffiliation.article_id",
        viewonly=True,
        order_by="PMCAffiliation.affiliation_order",
    )

    keywords: Mapped[List["Keyword"]] = relationship(
        "Keyword",
        primaryjoin="PMCArticle.id == Keyword.article_id",
        viewonly=True,
    )

