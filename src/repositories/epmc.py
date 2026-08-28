import logging
from datetime import datetime
import time
from typing import Any, Counter, Optional, Type, List

logger = logging.getLogger(__name__)

from src.models.citation import TotalCitations
from src.models.entities.pmc_article import PMCArticle, PMCAffiliation

import json

from sqlalchemy.orm import Session, selectinload, raiseload
from sqlalchemy.exc import OperationalError
from sqlalchemy import func, and_, or_, select, update as sa_update
from sqlalchemy.sql import literal_column
from src.config.constants import COUNTRIES, ALIASES

# Reusable ORM entities for cross-table queries
from src.models.entities.pmc_author import PMCAuthor, ArticleAuthor
from src.models.entities.extras import FullText, Grant
from src.models.entities.citations import Citation, Reference
from sqlalchemy import func
from src.models.entities.record import Record
from src.models.entities.ingestion import Ingestion
from src.models.entities.audit_log import AuditLog
from src.models.entities.pmc_review import PMCReview
from src.models.entities.known_divergence import KnownDivergence
class EPMCRepo:
    def __init__(self, db: Session):
        
        self.db = db
    
    def insert(self, entity: Any, entity_cls: Type[PMCArticle] = PMCArticle) -> int:
        # CHANGE: ORM-only insert. Expect an ORM entity instance.
        # Reason: Client now returns ORM objects; we no longer handle Pydantic dict conversion.
        if not isinstance(entity, entity_cls):
            raise TypeError(f"Expected instance of {entity_cls.__name__}, got {type(entity).__name__}")
        self.db.add(entity)
        self.db.flush()
        return entity.id

    def update(self, entity: Any, entity_cls: Type[PMCArticle] = PMCArticle) -> Optional[int]:
        # CHANGE: ORM-only update. Merge the given entity and flush.
        if not isinstance(entity, entity_cls):
            raise TypeError(f"Expected instance of {entity_cls.__name__}, got {type(entity).__name__}")
        merged = self.db.merge(entity)
        self.db.flush()
        return getattr(merged, "id", None)

    def commit_to_db(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def close(self) -> None:
        self.db.close()

    def get_by_id(self, entity_id: int, entity_cls: Type[PMCArticle] = PMCArticle):
        # CHANGE: Return ORM entity (no Pydantic validation).
        return self.db.get(entity_cls, entity_id)

    def get_by_source_id(self, source_id: str, entity_cls: Type[PMCArticle] = PMCArticle):
        # CHANGE: Use pm_id or pmc_id (PMCArticle has no source_id column).
        id_column = getattr(entity_cls, "pm_id", getattr(entity_cls, "pmc_id", None))
        if id_column is None:
            raise AttributeError(f"{entity_cls.__name__} has no 'pm_id' or 'pmc_id' column")
        return (
            self.db.query(entity_cls)
            .filter(id_column == source_id)
            .first()
        )

    def get_by_author_name(self, fullname: str, firstname: str, lastname: str) -> PMCAuthor | None:
        return (
            self.db.query(PMCAuthor)
            .join(ArticleAuthor, ArticleAuthor.author_id == PMCAuthor.id)
            # Optional: require association to an article (but DON'T join PMCAuthor again)
            .join(PMCArticle, PMCArticle.id == ArticleAuthor.article_id)
            .filter(
                PMCAuthor.fullname == fullname,
                PMCAuthor.firstname == firstname,
                PMCAuthor.lastname == lastname,
            )
            .first()
        )

    def get_grant(self, record_id: int, grant_id: Optional[str], agency: Optional[str], doi: Optional[str]) -> Grant | None:

        return (
            self.db.query(Grant)
            .filter(
                Grant.record_id == record_id,
                (Grant.grant_id == grant_id) if grant_id is not None else Grant.grant_id.is_(None),
                (Grant.agency == agency) if agency is not None else Grant.agency.is_(None),
                (Grant.doi == doi) if doi is not None else Grant.doi.is_(None),
            )
            .first()
        )

    def get_citation(self, article_id: int, citation_id: str) -> Citation | None:
        return (
            self.db.query(Citation)
            .filter(
                Citation.article_id == article_id,
                Citation.citation_id == citation_id,
            )
            .first()
        )
    def get_fulltext(self, article_id: int, url: str) -> FullText | None:
        return (
            self.db.query(FullText)
            .filter(
                FullText.article_id == article_id,
                FullText.url == url,
            )
            .first()
        )

    def get_articles_authors(self, article_id: int, author_id: int) -> ArticleAuthor | None:
        return (
            self.db.query(ArticleAuthor)
            .filter(
                ArticleAuthor.article_id == article_id,
                ArticleAuthor.author_id == author_id,
            )
            .first()
        )

    def get_reference(self, article_id: int, reference_id: str) -> Reference | None:
        return (
            self.db.query(Reference)
            .filter(
                Reference.article_id == article_id,
                Reference.reference_id == reference_id,
            )
            .first()
        )
    
    def get_affiliation(self, article_id: int, author_id: int) -> PMCAffiliation | None:
        return (
            self.db.query(PMCAffiliation)
            .filter(
                PMCAffiliation.article_id == article_id,
                PMCAffiliation.author_id == author_id,
            )
            .first()
        )

    def get_by_keyword(self, keyword: str, entity_cls: Type[PMCArticle] = PMCArticle) -> list:
        # CHANGE: Keyword.value is a PostgreSQL ARRAY(String); use .any(keyword) to emulate '= ANY(array)'.
        return (
            self.db.query(entity_cls)
            .join(Keyword, Keyword.article_id == entity_cls.id)
            .filter(Keyword.value.any(keyword))
            .all()
        )

    def get_articles_by_keyword(self, keyword: str, limit: int = 100, skip: int = 0) -> list[PMCArticle]:
        return (
            self.db.query(PMCArticle)
            .join(Record, PMCArticle.record_id == Record.id)
            .filter(Record.keyword.any(keyword))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_keyword_and_date(
        self,
        keyword: str,
        start_date: datetime,
        end_date: datetime,
        entity_cls: Type[PMCArticle] = PMCArticle,
    ) -> list:
        # CHANGE: Use a real date column; PMCArticle has 'first_publication_date'.
        # If your entity uses a different date field, update here.
        date_column = getattr(entity_cls, "first_publication_date", None)
        if date_column is None:
            date_column = getattr(entity_cls, "date_of_creation")  # fallback
        return (
            self.db.query(entity_cls)
            .join(Keyword, Keyword.article_id == entity_cls.id)
            .filter(
                Keyword.value.any(keyword),
                date_column.between(start_date, end_date),
            )
            .all()
        )

    def get_by_keyword_and_status(
        self,
        keyword: str,
        status: str,
        entity_cls: Type[PMCArticle] = PMCArticle,
    ) -> list:
        # CHANGE: PMCArticle uses 'publication_status'. Fallback to 'status' if present for other entities.
        status_column = getattr(entity_cls, "publication_status", getattr(entity_cls, "status", None))
        if status_column is None:
            raise AttributeError(f"{entity_cls.__name__} has no 'publication_status' or 'status' column")
        return (
            self.db.query(entity_cls)
            .join(Keyword, Keyword.article_id == entity_cls.id)
            .filter(
                Keyword.value.any(keyword),
                status_column == status,
            )
            .all()
        )

    def update_ingestion_count(self, entity, type):
        max_attempts = 5
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                entity_id = self.update(entity, type)
                return entity_id
            except OperationalError as e:
                logger.warning("ConnectionError on attempt %d/%d: %s", attempt, max_attempts, e)
                self.db.rollback()
                if attempt >= max_attempts:
                    logger.error("Max retry attempts reached, raising OperationalError")
                    raise
                # Exponential backoff, capped to 60s
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
            except Exception as e:
                logger.exception("Unexpected error during update_ingestion_count: %s", e)
                self.db.rollback()
                raise
                
    def insert_or_update(self, entity, type, update: bool):
        while True:
            try:
                if update:
                    # entity_id = self.update(entity, type)
                    entity_id = self.insert(entity, type)
                else:
                    entity_id = self.insert(entity, type)
                return entity_id
                #return 1   
            except OperationalError as e:
                logger.warning("ConnectionError: %s. Retrying after a timeout...", e)
                self.db.rollback()
                time.sleep(5)
            except Exception as e:
                logger.exception("Unexpected error during insert_or_update: %s", e)
                self.db.rollback()
                raise

    def get_all_articles(self, limit: int = 100, skip: int = 0) -> list[PMCArticle]:
        """
        Fetch articles with child relationships loaded, paginated.
        Returns only the latest version of each unique article (by pm_id).
        """
        # Create a window function subquery to rank articles by pm_id and ingestion version
        version_subq = (
            self.db.query(
                PMCArticle.id,
                func.row_number().over(
                    partition_by=PMCArticle.pm_id,
                    order_by=Ingestion.version.desc().nullslast()
                ).label('rn')
            )
            .outerjoin(Ingestion, PMCArticle.ingestion_id == Ingestion.id)
            .subquery()
        )
        
        # No relationship loading — the /epmc/all-articles endpoint serialises into
        # PMCArticleCustom which contains scalar fields only. Loading relationships
        # here added two extra queries per page (article_authors + affiliations)
        # for data that was immediately discarded, causing timeouts on large datasets.
        return (
            self.db.query(PMCArticle)
            .join(version_subq, and_(PMCArticle.id == version_subq.c.id, version_subq.c.rn == 1))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_total_unique_articles_count(self) -> int:
        """
        Get count of unique articles (by pm_id).
        Returns the total number of distinct pm_id values in pmc_articles.
        """
        count = self.db.query(func.count(func.distinct(PMCArticle.pm_id))).scalar()
        return int(count) if count else 0

    def get_all_grants(self, limit: int = 100, skip: int = 0) -> list[Grant]:
        return self.db.query(Grant).offset(skip).limit(limit).all()

    def get_funding_agencies(self, limit: int = 50) -> list[dict]:
        rows = (
            self.db.query(Grant.agency, func.count(Grant.id).label("count"))
            .filter(Grant.agency.isnot(None))
            .group_by(Grant.agency)
            .order_by(func.count(Grant.id).desc())
            .limit(limit)
            .all()
        )
        return [{"agency": agency, "count": int(count)} for agency, count in rows]

    def get_unique_funding_agencies_count(self) -> int:
        count = (
            self.db.query(func.count(func.distinct(Grant.agency)))
            .filter(Grant.agency.isnot(None))
            .scalar()
        )
        return int(count) if count else 0

    def get_all_pmc_authors(self, limit: int = 100, skip: int = 0) -> list[PMCAuthor]:
        return self.db.query(PMCAuthor).offset(skip).limit(limit).all()

    def _latest_article_id_by_pm_id(self, pm_id: str) -> Optional[int]:
        return (
            self.db.query(PMCArticle.id)
            .outerjoin(Ingestion, PMCArticle.ingestion_id == Ingestion.id)
            .filter(PMCArticle.pm_id == str(pm_id))
            .order_by(Ingestion.version.desc().nullslast(), PMCArticle.id.desc())
            .limit(1)
            .scalar()
        )

    def get_authors_by_article_id(self, article_id: int, limit: int = 100, skip: int = 0) -> list[tuple[PMCAuthor, Optional[int]]]:
        internal_id = self._latest_article_id_by_pm_id(str(article_id))
        if internal_id is None:
            try:
                internal_id = int(article_id)
            except Exception:
                return []

        return (
            self.db.query(PMCAuthor, ArticleAuthor.author_order)
            .join(ArticleAuthor, ArticleAuthor.author_id == PMCAuthor.id)
            .filter(ArticleAuthor.article_id == internal_id)
            .order_by(ArticleAuthor.author_order.asc().nullslast())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_affiliations_by_article_pm_id(self, pm_id: str, limit: int = 100, skip: int = 0) -> list[dict[str, Any]]:
        """
        Get affiliations for an article identified by pm_id, ordered by author appearance.

        Ordering is driven by articles_authors.author_order so affiliations align with
        the same author sequence used by author-related API responses.
        """
        latest_article_id = self._latest_article_id_by_pm_id(pm_id)
        if latest_article_id is None:
            return []

        rows = (
            self.db.query(
                PMCAffiliation.id,
                ArticleAuthor.article_id.label("article_id"),
                ArticleAuthor.author_id.label("author_id"),
                PMCAffiliation.org_name,
                PMCAffiliation.affiliation_order,
                PMCAuthor.firstname,
                PMCAuthor.lastname,
                PMCAuthor.fullname,
                ArticleAuthor.author_order,
            )
            .select_from(ArticleAuthor)
            .join(PMCAuthor, PMCAuthor.id == ArticleAuthor.author_id)
            .outerjoin(
                PMCAffiliation,
                and_(
                    PMCAffiliation.article_id == ArticleAuthor.article_id,
                    PMCAffiliation.author_id == ArticleAuthor.author_id,
                ),
            )
            .filter(ArticleAuthor.article_id == latest_article_id)
            .order_by(
                ArticleAuthor.author_order.asc().nullslast(),
                PMCAffiliation.affiliation_order.asc().nullslast(),
                PMCAffiliation.id.asc().nullslast(),
            )
            .all()
        )

        display_order_by_org: dict[str, int] = {}
        ordered_rows: list[dict[str, Any]] = []
        for row in rows:
            org_name = (row.org_name or "").strip()
            display_affiliation_order = None
            if org_name:
                if org_name not in display_order_by_org:
                    display_order_by_org[org_name] = len(display_order_by_org) + 1
                display_affiliation_order = display_order_by_org[org_name]

            ordered_rows.append(
                {
                    "id": row.id,
                    "pm_id": pm_id,
                    "article_id": row.article_id,
                    "author_id": row.author_id,
                    "author_order": row.author_order,
                    "firstname": row.firstname,
                    "lastname": row.lastname,
                    "fullname": row.fullname,
                    "org_name": org_name or None,
                    "affiliation_order": row.affiliation_order,
                    "display_affiliation_order": display_affiliation_order,
                }
            )

        return ordered_rows[skip: skip + limit]

    def get_articles_by_author_id(self, author_id: int, limit: int = 100, skip: int = 0) -> list[PMCArticle]:
        return (
            self.db.query(PMCArticle)
            .join(ArticleAuthor, ArticleAuthor.article_id == PMCArticle.id)
            .filter(ArticleAuthor.author_id == author_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_all_article_authors(self, limit: int = 100, skip: int = 0) -> list[ArticleAuthor]:
        return self.db.query(ArticleAuthor).offset(skip).limit(limit).all()

    def get_all_pmc_references(self, limit: int = 100, skip: int = 0) -> list[Reference]:
        return self.db.query(Reference).offset(skip).limit(limit).all()

    def get_all_citations(self, limit: int = 100, skip: int = 0) -> list[Citation]:
        return self.db.query(Citation).offset(skip).limit(limit).all()

    def get_all_fulltexts(self, limit: int = 100, skip: int = 0) -> list[FullText]:
        return self.db.query(FullText).offset(skip).limit(limit).all()

    def get_all_pmc_affiliations(self, limit: int = 100, skip: int = 0) -> list[PMCAffiliation]:
        return self.db.query(PMCAffiliation).offset(skip).limit(limit).all()

    def get_all_articles_ids(self) -> list[tuple[str | None, int]]:
        return  self.db.query(PMCArticle.pm_id, PMCArticle.record_id).all()
        

    def _get_latest_version_subquery(self, entity_class: Type[Any]):
        """
        Helper function to create a subquery that groups an entity by its primary key
        and returns (entity.id, max(ingestion.version)) for each unique entity.
        
        This encapsulates the grouping pattern used to get the latest version of each
        unique entity, avoiding duplication between version-tracking functions.
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            
        Returns:
            A subquery with columns 'id' and 'max_version'
        """
        return (
            self.db.query(
                entity_class.id,
                func.max(Ingestion.version).label('max_version')
            )
            .select_from(entity_class)
            .outerjoin(Ingestion, entity_class.ingestion_id == Ingestion.id)
            .group_by(entity_class.id)
            .subquery()
        )

    def _get_latest_version_subquery_by_column(self, entity_class: Type[Any], group_column):
        """
        Helper function to create a subquery that groups an entity by a custom column
        and returns (group_column, max(ingestion.version)) for each unique group.
        
        Useful for getting latest versions grouped by a business key (e.g., citation_id)
        rather than the primary key.
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            group_column: The column to group by (e.g., Citation.citation_id)
            
        Returns:
            A subquery with columns matching the group_column name and 'max_version'
        """
        return (
            self.db.query(
                group_column,
                func.max(Ingestion.version).label('max_version')
            )
            .select_from(entity_class)
            .outerjoin(Ingestion, entity_class.ingestion_id == Ingestion.id)
            .group_by(group_column)
            .subquery()
        )


    def _get_latest_entities(self, entity_class: Type[Any], limit: int = 100, skip: int = 0) -> list[Any]:
        """
        Get all latest versions of a given entity type grouped by their unique id.
        
        Returns only the highest ingestion version for each unique entity.
        Also handles entities without ingestion_id (includes those in results).
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            limit: Maximum number of entities to return (default: 100)
            skip: Number of entities to skip for pagination (default: 0)
            
        Returns:
            List of entity instances with the latest version for each unique entity
        """
        version_subq = self._get_latest_version_subquery(entity_class)
        
        return (
            self.db.query(entity_class)
            .join(version_subq, entity_class.id == version_subq.c.id)
            .outerjoin(Ingestion, entity_class.ingestion_id == Ingestion.id)
            .filter(
                (Ingestion.version == version_subq.c.max_version) |
                (entity_class.ingestion_id.is_(None))
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def _get_latest_entities_by_column(self, entity_class: Type[Any], group_column, limit: int = 100, skip: int = 0) -> list[Any]:
        """
        Get latest versions of entities grouped by a custom column (not primary key).
        
        For each unique value of group_column, returns only the entity with the highest
        ingestion version. Useful for getting unique business-keyed entities where
        different rows may represent different versions of the same logical entity.
        
        Uses a window function (row_number) approach for efficient pagination.
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            group_column: The column to group by (e.g., Citation.citation_id)
            limit: Maximum number of unique entities to return (default: 100)
            skip: Number of unique entities to skip for pagination (default: 0)
            
        Returns:
            List of entity instances with the latest version for each unique group
        """
        # Create a subquery that ranks rows within each group by ingestion version (descending)
        # Entities without ingestion_id get highest rank (treated as most recent)
        version_subq = (
            self.db.query(
                entity_class.id,
                func.row_number().over(
                    partition_by=group_column,
                    order_by=Ingestion.version.desc().nullslast()
                ).label('rn')
            )
            .outerjoin(Ingestion, entity_class.ingestion_id == Ingestion.id)
            .subquery()
        )
        
        # Query entities where row number is 1 (latest version per group)
        if entity_class == Citation:
            return (
                self.db.query(entity_class)
                .join(version_subq, and_(entity_class.id == version_subq.c.id, version_subq.c.rn == 1))
                .offset(skip)
                .all()
            )
        else:
            return (
                self.db.query(entity_class)
                .join(version_subq, and_(entity_class.id == version_subq.c.id, version_subq.c.rn == 1))
                .offset(skip)
                .limit(limit)
                .all()
            )


    def _get_entities_by_column_value(self, entity_class: Type[Any], column_name: str, value: Any, limit: int = 100, skip: int = 0) -> list[Any]:
        """
        Get entities filtered by a specific column value.
        
        Generic helper to fetch all instances of an entity where a given column matches a value.
        Useful for getting all child entities related to a parent (e.g., all keywords for an article).
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            column_name: The name of the column to filter on (as string)
            value: The value to match
            
        Returns:
            List of entity instances matching the filter
        """
        column = getattr(entity_class, column_name)
        return self.db.query(entity_class).filter(column == value).offset(skip).limit(limit).all()

    def _get_max_versions_by_columns(
        self,
        entity_class: Type[Any],
        columns: list,
        key_label: str,
        value_normalizer=None,
        skip_none_on_index: int = None
    ) -> dict[str, int]:
        """
        Get max ingestion version grouped by specified columns.
        
        Generic helper to query max(ingestion.version) grouped by one or more columns,
        returning a dict mapping formatted keys to version numbers.
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            columns: List of column objects to select and group by
            key_label: Label for the result key (e.g., "article", "grant", "fulltext")
            value_normalizer: Optional callable to transform/filter grouped values before key creation
                             Should accept a tuple of grouped values and return transformed tuple or None to skip
            skip_none_on_index: Optional index - skip rows where columns[skip_none_on_index] is None
            
        Returns:
            Dict mapping "label:val1:val2..." to max_version
        """
        result = {}
        
        query = self.db.query(*columns, func.max(Ingestion.version))
        
        # Join ingestion and filter by ingestion_id
        query = query.join(Ingestion, entity_class.ingestion_id == Ingestion.id)
        query = query.filter(entity_class.ingestion_id.isnot(None))
        query = query.group_by(*columns)
        
        for row in query.all():
            *values, max_ver = row
            
            # Handle None checks
            if skip_none_on_index is not None and values[skip_none_on_index] is None:
                continue
            
            # Apply normalization if provided
            if value_normalizer:
                normalized = value_normalizer(tuple(values))
                if normalized is None:
                    continue
                values = list(normalized)
            
            # Build key from label and values
            if len(values) == 1:
                key = f"{key_label}:{values[0]}"
            else:
                key = f"{key_label}:{':'.join(str(v) for v in values)}"
            
            result[key] = max_ver
        
        return result




    def get_max_version_by_source_id(self) -> dict[str, int]:
        """
        Returns a dict mapping a descriptive source-id key for every ePMC entity row
        to the highest ingestion.version value linked to that row via ingestion_id.

                Key format: "<table_label>:<source_identifier>"
                    articles       -> "article:<pm_id>"
                    authors        -> "author:<id>"
                    article_authors-> "article_author:<pm_id>:<author_id>"
                    affiliations   -> "affiliation:<pm_id>:<author_id>"
                    grants         -> "grant:<grant_id>"
                    fulltexts      -> "fulltext:<url>"
                    citations      -> "citation:<citation_id>"
                    references     -> "reference:<reference_id>"
        """
        result: dict[str, int] = {}

        # pmc_articles  ->  key: "article:<pm_id>"
        result.update(self._get_max_versions_by_columns(
            PMCArticle,
            [PMCArticle.pm_id],
            "article"
        ))

        # pmc_authors  ->  key: "author:<id>"
        result.update(self._get_max_versions_by_columns(
            PMCAuthor,
            [PMCAuthor.id],
            "author"
        ))

        # articles_authors  ->  key: "article_author:<pm_id>:<author_id>"
        # Need custom join for this one since it requires PMCArticle.pm_id
        for pm_id, author_id, max_ver in (
            self.db.query(PMCArticle.pm_id, ArticleAuthor.author_id, func.max(Ingestion.version))
            .join(ArticleAuthor, ArticleAuthor.article_id == PMCArticle.id)
            .join(Ingestion, ArticleAuthor.ingestion_id == Ingestion.id)
            .filter(ArticleAuthor.ingestion_id.isnot(None))
            .group_by(PMCArticle.pm_id, ArticleAuthor.author_id)
            .all()
        ):
            if pm_id is None:
                continue
            result[f"article_author:{pm_id}:{author_id}"] = max_ver

        # pmc_affiliations  ->  key: "affiliation:<pm_id>:<author_id>"
        # Also requires custom join for PMCArticle.pm_id
        for pm_id, author_id, max_ver in (
            self.db.query(PMCArticle.pm_id, PMCAffiliation.author_id, func.max(Ingestion.version))
            .join(PMCAffiliation, PMCAffiliation.article_id == PMCArticle.id)
            .join(Ingestion, PMCAffiliation.ingestion_id == Ingestion.id)
            .filter(PMCAffiliation.ingestion_id.isnot(None))
            .group_by(PMCArticle.pm_id, PMCAffiliation.author_id)
            .all()
        ):
            if pm_id is None:
                continue
            result[f"affiliation:{pm_id}:{author_id}"] = max_ver

        # grants  ->  key: "grant:<grant_id>"
        result.update(self._get_max_versions_by_columns(
            Grant,
            [Grant.grant_id],
            "grant"
        ))

        # fulltexts  ->  key: "fulltext:<normalized_url>"
        def normalize_url(values):
            """Normalize URL for consistent key matching."""
            url = values[0]
            if url is None:
                return None
            norm = str(url).strip().lower()
            if norm.endswith("/"):
                norm = norm.rstrip("/")
            if not norm:
                return None
            return (norm,)
        
        result.update(self._get_max_versions_by_columns(
            FullText,
            [FullText.url],
            "fulltext",
            value_normalizer=normalize_url
        ))

        # citations  ->  key: "citation:<citation_id>"
        result.update(self._get_max_versions_by_columns(
            Citation,
            [Citation.citation_id],
            "citation"
        ))

        # pmc_references  ->  key: "reference:<reference_id>"
        result.update(self._get_max_versions_by_columns(
            Reference,
            [Reference.reference_id],
            "reference"
        ))

        return result


    def get_highest_ingestion_version(self) -> int:
        """Return the highest `version` value from the `ingestion` table.

        Returns 0 if there are no ingestion rows.
        """
        max_ver = self.db.query(func.max(Ingestion.version)).scalar()
        try:
            return int(max_ver) if max_ver is not None else 0
        except Exception:
            logger.warning("Could not parse max ingestion version: %r", max_ver)
            return 0

    def get_last_ingestion_date(self) -> Optional[datetime]:
        """Return the most recent ingested_at timestamp of a SUCCESSFUL run.

        A run is considered successful when total_pulled is not NULL — that value
        is written by update_ingestion_counts() only after classification completes.
        Failed runs leave total_pulled as NULL and are excluded so their committed
        ingestion row does not corrupt the next delta window.
        """
        return (
            self.db.query(func.max(Ingestion.ingested_at))
            .filter(Ingestion.total_pulled.isnot(None))
            .scalar()
        )

    def update_ingestion_counts(self, ingestion_id: int, counts: dict) -> None:
        self.db.execute(
            sa_update(Ingestion).where(Ingestion.id == ingestion_id).values(**counts)
        )
        self.db.flush()

    # ------------------------------------------------------------------
    # Curation — audit log
    # ------------------------------------------------------------------

    def insert_audit_log(self, audit_log: AuditLog) -> int:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log.id

    # ------------------------------------------------------------------
    # Curation — review
    # ------------------------------------------------------------------

    def insert_review(self, review: PMCReview) -> int:
        self.db.add(review)
        self.db.flush()
        return review.id

    def get_pending_review_by_epmc_id(self, epmc_id: str) -> Optional[PMCReview]:
        """Return the active pending pmc_review row for an article, if one exists."""
        return (
            self.db.execute(
                select(PMCReview)
                .where(PMCReview.epmc_id == epmc_id)
                .where(PMCReview.review_status == "pending")
                .order_by(PMCReview.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        )

    def update_review(self, review_id: int, updates: dict) -> None:
        """Overwrite fields on an existing pmc_review row (used to refresh stale pending rows)."""
        self.db.execute(
            sa_update(PMCReview).where(PMCReview.id == review_id).values(**updates)
        )
        self.db.flush()

    # ------------------------------------------------------------------
    # Curation — article lookups (used by AutoClassifyService)
    # ------------------------------------------------------------------

    def get_staged_articles(self, ingestion_id: int) -> List[PMCArticle]:
        """Return all pmc_articles rows written in a given ingestion run."""
        return (
            self.db.execute(select(PMCArticle).where(PMCArticle.ingestion_id == ingestion_id))
            .scalars()
            .all()
        )

    def get_article_by_epmc_id(self, epmc_id: str) -> Optional[PMCArticle]:
        # Use first() — production DB may have duplicate epmc_id rows from pre-curation
        # data. Take the row with the highest id (most recently approved version).
        return (
            self.db.execute(
                select(PMCArticle)
                .where(PMCArticle.epmc_id == epmc_id)
                .order_by(PMCArticle.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        )

    def get_article_by_doi(self, doi: str) -> Optional[PMCArticle]:
        # Same defensive approach for doi lookups.
        return (
            self.db.execute(
                select(PMCArticle)
                .where(PMCArticle.doi == doi)
                .order_by(PMCArticle.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        )

    def get_active_known_divergences(
        self, epmc_id: Optional[str], doi: Optional[str]
    ) -> List[KnownDivergence]:
        """Return active known_divergence rows for a given article identity."""
        if not epmc_id and not doi:
            return []
        query = select(KnownDivergence).where(KnownDivergence.active.is_(True))
        if epmc_id:
            query = query.where(KnownDivergence.epmc_id == epmc_id)
        else:
            query = query.where(KnownDivergence.doi == doi)
        return self.db.execute(query).scalars().all()
        
    def get_all_latest_entries(self, pm_id: Optional[str] = None, limit: int = 100, skip: int = 0) -> dict[str, list[Any]]:
        """
        Get all unique entries from all tables with the most recent version FOR EACH ENTITY.
        
        For each unique entity (by pm_id, author_id, etc), returns only the version with the
        highest ingestion.version. This means an article can be on version 4 while the latest
        ingestion in the system is version 7 - we still return that article version 4.
        
        If pm_id is provided, returns only data associated with that specific article.
        Otherwise, returns latest version of every unique entity across all tables.
        
        Args:
            pm_id: Optional PubMed ID (source_id) to filter by a specific article
            limit: Maximum number of entities to return per table (default: 100)
            skip: Number of entities to skip per table for pagination (default: 0)
        
        Returns:
            A dictionary with table names as keys and lists of latest entries as values.
        """
        result = {}
        
        if pm_id:
            # Get the specific article first
            article = (
                self.db.query(PMCArticle)
                .filter(PMCArticle.pm_id == pm_id)
                .first()
            )
            if not article:
                # Article not found, return empty result
                return {
                    'pmc_articles': [],
                    'pmc_authors': [],
                    'pmc_affiliations': [],
                    'articles_authors': [],
                    'citations': [],
                    'pmc_references': [],
                    'grants': [],
                    'fulltexts': []
                }
            
            article_id = article.id
            record_id = article.record_id
            
            result['pmc_articles'] = [article]
            
            # Get authors for this article (reuse existing method)
            result['pmc_authors'] = self.get_authors_by_article_id(article_id, limit=limit, skip=skip)
            
            # Get all other article-related entities by article_id
            result['pmc_affiliations'] = self._get_entities_by_column_value(PMCAffiliation, 'article_id', article_id, limit=limit, skip=skip)
            result['articles_authors'] = self._get_entities_by_column_value(ArticleAuthor, 'article_id', article_id, limit=limit, skip=skip)
            result['citations'] = self._get_entities_by_column_value(Citation, 'article_id', article_id, limit=limit, skip=skip)
            result['pmc_references'] = self._get_entities_by_column_value(Reference, 'article_id', article_id, limit=limit, skip=skip)
            result['fulltexts'] = self._get_entities_by_column_value(FullText, 'article_id', article_id, limit=limit, skip=skip)
            
            # Get grants for the same record (by record_id)
            result['grants'] = self._get_entities_by_column_value(Grant, 'record_id', record_id, limit=limit, skip=skip)
        else:
            # Get latest version of each UNIQUE entity across all tables with pagination
            result['pmc_articles'] = self._get_latest_entities(PMCArticle, limit=limit, skip=skip)
            result['pmc_authors'] = self._get_latest_entities(PMCAuthor, limit=limit, skip=skip)
            result['pmc_affiliations'] = self._get_latest_entities(PMCAffiliation, limit=limit, skip=skip)
            result['articles_authors'] = self._get_latest_entities(ArticleAuthor, limit=limit, skip=skip)
            result['citations'] = self._get_latest_entities(Citation, limit=limit, skip=skip)
            result['pmc_references'] = self._get_latest_entities(Reference, limit=limit, skip=skip)
            result['grants'] = self._get_latest_entities(Grant, limit=limit, skip=skip)
            result['fulltexts'] = self._get_latest_entities(FullText, limit=limit, skip=skip)
        
        return result

    def get_unique_articles(self, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Get count of articles by unique pm_id.
        
        Returns the number of occurrences for each unique pm_id in the pmc_articles table.
        
        Args:
            limit: Maximum number of unique pm_ids to return (default: 100)
            skip: Number of unique pm_ids to skip for pagination (default: 0)
            
        Returns:
            Dict mapping pm_id to count of occurrences
        """
        return self._get_count_by_column(PMCArticle, PMCArticle.pm_id, skip_none=True, limit=limit, skip=skip)

    def get_unique_grants(self, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Get count of grants by unique grant_id.
        
        Returns the number of occurrences for each unique grant_id in the grants table.
        Note: grant_id may be None/empty in some rows.
        
        Args:
            limit: Maximum number of unique grant_ids to return (default: 100)
            skip: Number of unique grant_ids to skip for pagination (default: 0)
            
        Returns:
            Dict mapping grant_id to count of occurrences
        """
        return self._get_count_by_column(Grant, Grant.grant_id, skip_none=False, limit=limit, skip=skip)

    def get_unique_authors(self, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Get count of authors by unique firstname+lastname combination.
        
        Returns the number of occurrences for each unique author name in the pmc_authors table.
        
        Args:
            limit: Maximum number of unique author combinations to return (default: 100)
            skip: Number of unique author combinations to skip for pagination (default: 0)
            
        Returns:
            Dict mapping "firstname:lastname" to count of occurrences
        """
        result = {}
        query = (self.db.query(
            PMCAuthor.firstname,
            PMCAuthor.lastname,
            func.count().label('count')
        ).group_by(PMCAuthor.firstname, PMCAuthor.lastname)
        .offset(skip)
        .limit(limit))
        
        for firstname, lastname, count in query.all():
            key = f"{firstname}:{lastname}"
            result[key] = count
        
        return result

    def get_top_authors(self, count: int = 15) -> list[dict]:
        """
        Return the top authors by number of article associations.

        Args:
            count: number of top rows to return

        Returns:
            List of dicts with keys: author_count, author_id, author
        """
        query = (
            self.db.query(
                func.count(ArticleAuthor.author_id).label('author_count'),
                ArticleAuthor.author_id,
                func.concat(PMCAuthor.firstname, ' ', PMCAuthor.lastname).label('author')
            )
            .join(PMCArticle, PMCArticle.id == ArticleAuthor.article_id)
            .join(PMCAuthor, PMCAuthor.id == ArticleAuthor.author_id)
            .group_by(ArticleAuthor.author_id, PMCAuthor.firstname, PMCAuthor.lastname)
            .order_by(func.count(ArticleAuthor.author_id).desc(), PMCAuthor.lastname, PMCAuthor.firstname)
        )

        result: list[dict] = []
        for author_count, author_id, author in query.all():
            result.append({
                'author_count': int(author_count),
                'author_id': int(author_id),
                'author': author,
            })

        return result

    def get_unique_references(self, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Get count of references by unique reference_id.
        
        Returns the number of occurrences for each unique reference_id in the pmc_references table.
        Note: reference_id may be None/empty in some rows.
        
        Args:
            limit: Maximum number of unique reference_ids to return (default: 100)
            skip: Number of unique reference_ids to skip for pagination (default: 0)
            
        Returns:
            Dict mapping reference_id to count of occurrences
        """
        return self._get_count_by_column(Reference, Reference.reference_id, skip_none=False, limit=limit, skip=skip)

    def get_unique_fulltexts(self, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Get count of fulltexts by unique url.
        
        Returns the number of occurrences for each unique url in the fulltexts table.
        
        Args:
            limit: Maximum number of unique urls to return (default: 100)
            skip: Number of unique urls to skip for pagination (default: 0)
            
        Returns:
            Dict mapping url to count of occurrences
        """
        return self._get_count_by_column(FullText, FullText.url, skip_none=True, limit=limit, skip=skip)

    def get_affiliation_countries_count(self) -> dict[str, int]:
        """
        Extract countries from pmc_affiliations org_name and return count by country.
        
        Extracts the country from org_name strings in format:
        "Organization text, Country."
        The country is the text after the last comma and before the period.
        
        Returns:
            Dictionary mapping country names to their occurrence counts in affiliations.
            Example: {"China": 42, "USA": 15, "Japan": 8}
        """
        affiliations = self.db.query(PMCAffiliation.org_name).all()
        
        country_count: dict[str, int] = {}
        
        # Prepare sorted country names for longest-first matching
        sorted_countries = sorted(COUNTRIES, key=lambda s: len(s), reverse=True)

        # Normalize alias keys for quick lookup
        alias_items = [(k.lower(), v) for k, v in ALIASES.items()]

        for (org_name,) in affiliations:
            if not org_name:
                continue

            normalized = org_name.lower()
            found_country = None

            # 1) Check aliases first (e.g., 'USA', 'UK', 'U.S.A.')
            for alias, canonical in alias_items:
                if alias in normalized:
                    found_country = canonical
                    break

            if found_country:
                country_count[found_country] = country_count.get(found_country, 0) + 1
                continue

            # 2) Check full country names (longest-first)
            for country in sorted_countries:
                if country.lower() in normalized:
                    found_country = country
                    break

            if found_country:
                country_count[found_country] = country_count.get(found_country, 0) + 1
                continue

            # 3) Fallback to legacy parsing: text after last "," and before "."
            try:
                last_comma_idx = org_name.rfind(',')
                if last_comma_idx == -1:
                    continue

                period_idx = org_name.find('.', last_comma_idx)
                if period_idx == -1:
                    country = org_name[last_comma_idx + 1:].strip()
                else:
                    country = org_name[last_comma_idx + 1:period_idx].strip()

                if country:
                    country_count[country] = country_count.get(country, 0) + 1
            except Exception:
                logger.debug("Could not parse country from org_name: %r", org_name)
                continue
        
        return country_count

    def _get_count_by_column(self, entity_class: Type[Any], column, skip_none: bool = False, limit: int = 100, skip: int = 0) -> dict[str, int]:
        """
        Count occurrences of each unique value in a specified column.
        
        Groups by the column and returns a dict mapping unique values to their counts.
        Useful for getting unique identifier counts (e.g., citation_id, pm_id, grant_id).
        
        Args:
            entity_class: The SQLAlchemy entity class to query
            column: The column to group by and count
            skip_none: If True, skip rows where column value is None
            limit: Maximum number of unique values to return (default: 100)
            skip: Number of unique values to skip for pagination (default: 0)
            
        Returns:
            Dict mapping unique column values to their occurrence counts
        """
        result = {}
        
        query = self.db.query(column, func.count().label('count')).group_by(column)
        
        if skip_none:
            query = query.filter(column.isnot(None))
        
        query = query.offset(skip).limit(limit)
        
        for value, count in query.all():
            key = str(value) if value is not None else "<null>"
            result[key] = count
        
        return result

    def get_unique_citations(self, limit: int = 100, skip: int = 0) -> list[Citation]:
        """
        Get unique citations by (article_id, citation_id) pair with the highest ingestion version.
        
        For each unique (article_id, citation_id) pair, returns only the Citation entity
        with the highest ingestion version. If a citation row has no ingestion_id, it is
        included in the results.
        
        Args:
            limit: Maximum number of unique citations to return (default: 100)
            skip: Number of unique citations to skip for pagination (default: 0)
            
        Returns:
            List of Citation entities, one per unique (article_id, citation_id) pair with highest version
        """
        return self._get_latest_entities_by_column(Citation, [Citation.article_id, Citation.citation_id], limit=limit, skip=skip)
    
    def get_total_citations_count_by_year(self) -> list[tuple[int, int]]:
        """Return yearly citation counts as (pub_year, year_count)."""
        return (
            self.db.query(
                Citation.pub_year,
                func.count(Citation.id).label("year_count"),
            )
            .filter(Citation.pub_year.isnot(None))
            .group_by(Citation.pub_year)
            .order_by(Citation.pub_year.asc())
            .all()
        )

    def get_total_cited_by_count(self) -> int:
        """Sum cited_by_count across all articles in pmc_articles."""
        total = self.db.query(func.sum(PMCArticle.cited_by_count)).scalar()
        return int(total) if total else 0

    def count_unique_authors(self) -> int:
        """
        Count distinct authors linked to the deduplicated article set.
        Mirrors the same row_number() dedup used by get_all_articles() so the
        number is consistent with the 1-row-per-pm_id article count.
        """
        version_subq = (
            self.db.query(
                PMCArticle.id,
                func.row_number().over(
                    partition_by=PMCArticle.pm_id,
                    order_by=Ingestion.version.desc().nullslast(),
                ).label("rn"),
            )
            .outerjoin(Ingestion, PMCArticle.ingestion_id == Ingestion.id)
            .subquery()
        )

        deduped_ids_subq = (
            self.db.query(PMCArticle.id)
            .join(version_subq, and_(PMCArticle.id == version_subq.c.id, version_subq.c.rn == 1))
            .subquery()
        )

        count = (
            self.db.query(func.count(func.distinct(ArticleAuthor.author_id)))
            .filter(ArticleAuthor.article_id.in_(self.db.query(deduped_ids_subq.c.id)))
            .scalar()
        )
        return int(count) if count else 0
        
    def count_articles(self) -> int:
        count = self.db.query(func.count(func.distinct(PMCArticle.pm_id))).scalar()
        return int(count) if count else 0

    def get_articles_for_dashboard(self) -> list[dict]:
        from sqlalchemy import text
        sql = """
            SELECT DISTINCT ON (a.pm_id)
                a.pm_id,
                a.title,
                a.doi,
                a.pub_year,
                a.cited_by_count,
                a.is_open_access,
                a.abstract_text,
                a.language,
                a.affiliation
            FROM pmc_articles a
            LEFT JOIN ingestion i ON a.ingestion_id = i.id
            WHERE a.pm_id IS NOT NULL
            ORDER BY a.pm_id, i.version DESC NULLS LAST
        """
        rows = self.db.execute(text(sql))
        return [
            {
                "pm_id":          r.pm_id or "",
                "title":          r.title or "",
                "doi":            r.doi or "",
                "pub_year":       r.pub_year,
                "cited_by_count": r.cited_by_count or 0,
                "is_open_access": str(r.is_open_access).lower() in ("y", "yes", "true", "1"),
                "abstract_text":  r.abstract_text or "",
                "language":       r.language or "",
                "affiliation":    r.affiliation or "",
            }
            for r in rows
        ]

    def get_publication_types(self) -> list[dict]:
        from sqlalchemy import text
        sql = """
            WITH ranked AS (
                SELECT a.id,
                       row_number() OVER (
                           PARTITION BY a.pm_id
                           ORDER BY i.version DESC NULLS LAST
                       ) AS rn
                FROM pmc_articles a
                LEFT JOIN ingestion i ON a.ingestion_id = i.id
                WHERE a.pm_id IS NOT NULL
            ),
            deduped AS (
                SELECT r.id FROM ranked r WHERE r.rn = 1
            )
            SELECT
                CASE
                    WHEN a.pub_type::text ILIKE '%Preprint%'        THEN 'Preprint'
                    WHEN a.pub_type::text ILIKE '%Review%'          THEN 'Review'
                    WHEN a.pub_type::text ILIKE '%Comment%'
                      OR a.pub_type::text ILIKE '%Letter%'
                      OR a.pub_type::text ILIKE '%Editorial%'       THEN 'Comment / Letter'
                    WHEN a.pub_type::text ILIKE '%Journal Article%' THEN 'Journal Article'
                    ELSE 'Other'
                END AS primary_type,
                COUNT(*) AS count
            FROM pmc_articles a
            JOIN deduped d ON a.id = d.id
            WHERE a.pub_type IS NOT NULL
            GROUP BY primary_type
            ORDER BY count DESC
        """
        result = self.db.execute(text(sql))
        return [{"type": row.primary_type, "count": int(row.count)} for row in result]
