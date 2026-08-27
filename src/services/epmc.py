import logging
from datetime import datetime
from typing import Any, Counter, List, Optional
from src.clients.epmc import EPMCClient
from src.models.citation import CitationOverYears, TotalCitations
from src.models.entities.pmc_article import PMCArticle
from src.models.entities.pmc_author import PMCAuthor, PMCAffiliation, ArticleAuthor
from src.models.entities.extras import Grant, FullText, Keyword
from src.models.entities.citations import Citation, Reference
from src.models.entities.record import Record, RecordType, Source, Status, ProductType
from src.models.entities.ingestion import Ingestion
from src.models.entities.audit_log import AuditLog
from src.models.entities.enums import AuditEventType
from src.repositories.epmc import EPMCRepo

logger = logging.getLogger(__name__)

class EPMCService:
    def __init__(self, repo: EPMCRepo) -> None:
        self.epmc_repo = repo
        self.epmc_client = EPMCClient()
        # Defer heavy DB loads to avoid blocking startup. These maps will be
        # populated on first use by calling the loader helpers.
        self.articles_records: dict[str, int] = {}
        self.highest_versions_by_source_id: dict[str, int] = {}
        self.ingested_articles: dict[int, int] = {}
        self.ingestion_id = None

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _detect_run_type(self) -> tuple:
        """
        Auto-detect whether the next ingestion should be a full or delta pull.

        Returns (run_type, from_date) where from_date is a YYYY-MM-DD string
        for delta runs, or None for full runs.
        """
        last_date = self.epmc_repo.get_last_ingestion_date()
        if last_date is None:
            return "full", None
        return "delta", last_date.strftime("%Y-%m-%d")

    @staticmethod
    def _positive_int(value):
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @classmethod
    def _ordered_value(cls, payload, keys: tuple[str, ...], fallback: int) -> int:
        if isinstance(payload, dict):
            for key in keys:
                parsed = cls._positive_int(payload.get(key))
                if parsed is not None:
                    return parsed
        return fallback

    def _load_articles_records(self) -> dict[str, int]:
        article_rows = self.epmc_repo.get_all_articles_ids()
        return {
            pm_id: record_id
            for pm_id, record_id in article_rows
            if pm_id is not None
        }
    
    def _load_versions_by_source_id(self) -> dict[str, int]:
        return self.epmc_repo.get_max_version_by_source_id()

    def list_fulltext_keys(self) -> list[str]:
        """Return all keys from the in-memory version map that start with 'fulltext:'."""
        if not self.highest_versions_by_source_id:
            return []
        return [k for k in self.highest_versions_by_source_id.keys() if k.startswith("fulltext:")]

    def _next_ingestion_version(self) -> int:
        try:
            return self.epmc_repo.get_highest_ingestion_version() + 1
        except Exception:
            logger.warning("Could not fetch highest ingestion version; defaulting to 1")
            return 1

    # ------------------------------------------------------------------
    # Ingestion lifecycle audit events
    # ------------------------------------------------------------------

    def record_ingestion_started(self, keyword: str, run_type: str = "full", created_by: str = "system") -> None:
        self.epmc_repo.insert_audit_log(AuditLog(
            event_type=AuditEventType.INGESTION_STARTED,
            entity_type="ingestion",
            new_value={"keyword": keyword, "run_type": run_type},
            action_by=created_by,
            action_at=datetime.utcnow(),
        ))

    def record_ingestion_completed(
        self, ingestion_id: int, keyword: str, classify_result: Any, created_by: str = "system"
    ) -> None:
        self.epmc_repo.insert_audit_log(AuditLog(
            event_type=AuditEventType.INGESTION_COMPLETED,
            entity_type="ingestion",
            entity_id=str(ingestion_id),
            ingestion_id=ingestion_id,
            new_value={
                "keyword": keyword,
                "total_pulled": classify_result.total_pulled,
                "new_count": classify_result.new_count,
                "unchanged_count": classify_result.unchanged_count,
                "changed_count": classify_result.changed_count,
                "auto_approved_count": classify_result.auto_approved_count,
                "pending_review_count": classify_result.pending_review_count,
                "unresolvable_count": classify_result.unresolvable_count,
            },
            action_by=created_by,
            action_at=datetime.utcnow(),
        ))

    def record_ingestion_failed(
        self, ingestion_id: Optional[int], keyword: str, error: str, created_by: str = "system"
    ) -> None:
        try:
            self.epmc_repo.insert_audit_log(AuditLog(
                event_type=AuditEventType.INGESTION_FAILED,
                entity_type="ingestion",
                entity_id=str(ingestion_id) if ingestion_id else None,
                ingestion_id=ingestion_id,
                new_value={"error": error, "keyword": keyword},
                action_by=created_by,
                action_at=datetime.utcnow(),
            ))
        except Exception:
            logger.exception("Failed to write INGESTION_FAILED audit log")

    def insert_articles_by_keyword(
        self,
        keyword: str,
        created_by: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict[str, int]:
        # Explicit date range → always a delta pull, no auto-detect needed.
        # No dates → auto-detect: delta if prior ingestion exists, full otherwise.
        if from_date:
            run_type = "delta"
            effective_to = to_date or datetime.utcnow().strftime("%Y-%m-%d")
            logger.info(
                "Delta pull (explicit): keyword=%s from_date=%s to_date=%s",
                keyword, from_date, effective_to,
            )
            json_response = self.epmc_client.get_delta_articles(keyword, from_date, effective_to)
        else:
            run_type, detected_from = self._detect_run_type()
            effective_to = datetime.utcnow().strftime("%Y-%m-%d")
            if run_type == "delta":
                logger.info(
                    "Delta pull (auto): keyword=%s from_date=%s to_date=%s",
                    keyword, detected_from, effective_to,
                )
                json_response = self.epmc_client.get_delta_articles(keyword, detected_from, effective_to)
            else:
                logger.info("Full pull: keyword=%s", keyword)
                json_response = self.epmc_client.get_articles(keyword)

        results = json_response.get("resultList", {}).get("result", []) or []

        ingestion_version = self._next_ingestion_version()
        ingestion_model = self.epmc_client.create_ingestion(
            ingestion_version,
            keyword=keyword,
            run_type=run_type,
            created_by=created_by,
        )
        ingestion_id = self.epmc_repo.insert_or_update(ingestion_model, Ingestion, False)
        self.ingestion_id = ingestion_id

        counts = {"records": 0, "articles": 0, "grants": 0, "citations": 0, "references": 0, "fulltexts": 0, "authors": 0, "article_authors": 0, "affiliations": 0}

        try:
            for article in results: 
                
                is_update = self.articles_records.get(article.get("id")) is not None

                # Record
                article_record_model = self.epmc_client.create_record("ARTICLE", keyword)
                article_record_id = self.epmc_repo.insert_or_update(article_record_model, Record, is_update)
                counts["records"] += 1


                citation_data = self.epmc_client.get_citations(article.get("id"), source=article.get("source"))

                # Article
                logger.debug("Citation hitCount for article %s: %s", article.get("id"), citation_data.get("hitCount"))
                article_entity = self.epmc_client.create_article(article, article_record_id, ingestion_id, created_by=created_by, cited_by=citation_data.get("hitCount", 0))
                article_id = self.epmc_repo.insert_or_update(article_entity, PMCArticle, is_update)
                counts["articles"] += 1
                self.ingested_articles[article.get("id")] = article_id

                for cite in (citation_data.get("citationList") or {}).get("citation") or []:
                    existing_citation = False

                    # Citation
                    citation_entity = self.epmc_client.create_citation(cite, article_id, self.ingestion_id, created_by=created_by)
                    citation_id = self.epmc_repo.insert_or_update(citation_entity, Citation, existing_citation)
                    counts["citations"] += 1

                if article_id not in self.articles_records:
                    self.articles_records[article_id] = article_record_id

                # Grants 
                for grant_data in (article.get("grantsList") or {}).get("grant") or []:                        

                    grant_entity = self.epmc_client.create_grant(grant_data, article_record_id, ingestion_id, created_by=created_by)
                    grant_id = self.epmc_repo.insert_or_update(grant_entity, Grant, is_update)
                    counts["grants"] += 1

                # Fulltext
                for ft in (article.get("fullTextUrlList") or {}).get("fullTextUrl") or []:
                    fulltext_entity = self.epmc_client.create_fulltext(article_id, ft, ingestion_id, created_by=created_by)
                    fulltext_id = self.epmc_repo.insert_or_update(fulltext_entity, FullText, is_update)
                    counts["fulltexts"] += 1
            
                fallback_author_order = 1
                for author in self._as_list((article.get("authorList") or {}).get("author")):
                    if not isinstance(author, dict):
                        continue

                    author_order = self._ordered_value(
                        author,
                        ("authorOrder", "author_order", "order"),
                        fallback_author_order,
                    )
                    fallback_author_order += 1

                    # Authors
                    existing = self.epmc_repo.get_by_author_name(author.get("fullName"), author.get("firstName"), author.get("lastName"))
                    if existing is None:
                        author_entity = self.epmc_client.create_author(author, ingestion_id, created_by=created_by)
                        author_id = self.epmc_repo.insert_or_update(author_entity, PMCAuthor, is_update)
                        counts["authors"] += 1
                    else:
                        author_id = existing.id
                        counts["authors"] += 1

                    # Article_authors
                    existing_article_author = self.highest_versions_by_source_id.get(
                        f"article_author:{article.get('id')}:{author_id}", 0
                    ) > 0
                           
                    article_author_entity = self.epmc_client.create_article_author(article_id, author_id, author_order, ingestion_id, created_by=created_by)
                    article_author_id = self.epmc_repo.insert_or_update(article_author_entity, ArticleAuthor, existing_article_author)
                    counts["article_authors"] += 1
                
                    # Affiliations
                    fallback_affiliation_order = 1
                    affiliations = self._as_list((author.get("authorAffiliationDetailsList") or {}).get("authorAffiliation"))
                    for aff in affiliations:
                        org_name = aff.get("affiliation") if isinstance(aff, dict) else aff
                        if org_name:
                            aff_order = self._ordered_value(
                                aff,
                                ("affiliationOrder", "affiliation_order", "authorAffiliationOrder", "order"),
                                fallback_affiliation_order,
                            )
                            affiliation_entity = self.epmc_client.create_affiliation(aff, author_id, article_id, aff_order, ingestion_id, created_by=created_by)
                            affiliation_id = self.epmc_repo.insert_or_update(affiliation_entity, PMCAffiliation, is_update)
                            counts["affiliations"] += 1
                            fallback_affiliation_order += 1
            
            ingestion_model = self.epmc_client.update_ingestion(self.ingestion_id, counts["articles"])
            self.epmc_repo.update_ingestion_count(ingestion_model, Ingestion)
            self.epmc_repo.commit_to_db()
        except Exception:
            self.epmc_repo.rollback()
            raise
        logger.info("Article ingestion complete: %s", counts)
        return counts
    
    def insert_citations(self, created_by: str):
        
        counts = {"citations": 0}
        try:
            if self.ingestion_id is None:
                raise ValueError("Ingestion ID is not set. Please run insert_articles_by_keyword first.")

            for article_id in self.ingested_articles:
                citation_data = self.epmc_client.get_citations(article_id, source=self.ingested_articles[article_id].get("source"))
                for cite in (citation_data.get("citationList") or {}).get("citation") or []:
                    #existing_citation = self.epmc_repo.get_citation(article_id, cite.get("citation_id")) is not None
                    existing_citation = False

                    # Citation
                    citation_entity = self.epmc_client.create_citation(cite, self.ingested_articles[article_id], self.ingestion_id, created_by=created_by)
                    citation_id = self.epmc_repo.insert_or_update(citation_entity, Citation, existing_citation)
                    counts["citations"] += 1

            self.epmc_repo.commit_to_db()
        except Exception:
            self.epmc_repo.rollback()
            raise
        return counts

    def insert_references(self, created_by: str, use_db_articles: bool = False):

        counts = {"references": 0}

        # Determine article list: either use self.ingested_articles (from recent ingestion)
        # or fetch all current articles from the database
        if use_db_articles:
            # Fetch all articles from DB; use pm_id as key and internal id for FK
            db_articles = self.epmc_repo.get_all_articles(limit=10000)
            article_map = {str(a.pm_id): a.id for a in db_articles if a.pm_id is not None}
        else:
            # Use articles from recent ingestion (self.ingested_articles key=pm_id, value=internal_id)
            article_map = self.ingested_articles
            if article_map is None:
                raise ValueError("Ingestion ID is not set and use_db_articles is False. Please run insert_articles_by_keyword first or set use_db_articles=True.")
            if not article_map:
                logger.info("insert_references: no articles in this ingestion run, skipping")
                return counts

        # Create ingestion if needed (for standalone reference ingestion with no prior article run)
        if self.ingestion_id is None:
            ingestion_version = self._next_ingestion_version()
            ingestion_model = self.epmc_client.create_ingestion(
                ingestion_version,
                run_type="full",
                created_by=created_by,
            )
            self.ingestion_id = self.epmc_repo.insert_or_update(ingestion_model, Ingestion, False)

        try:
            for pm_id, article_id in article_map.items():
                response = self.epmc_client.get_references(pm_id, source=article_map[pm_id].get("source") if use_db_articles else "MED")
                reference_items = (response.get("referenceList") or {}).get("reference") or []

                if isinstance(reference_items, dict):
                    reference_items = [reference_items]

                for ref in reference_items:
                    existing_reference = False
                    reference_entity = self.epmc_client.create_reference(ref, article_id, self.ingestion_id, created_by=created_by)
                    reference_id = self.epmc_repo.insert_or_update(reference_entity, Reference, existing_reference)
                    counts["references"] += 1

            self.epmc_repo.commit_to_db()
        except Exception:
            self.epmc_repo.rollback()
            raise

        return counts
    
    def get_unique_authors_count(self) -> int:
        return self.epmc_repo.count_unique_authors()
    
    def get_articles_count(self) -> int:
        return self.epmc_repo.count_articles()
    
    def get_cumulative_citations(self) -> TotalCitations:
        year_counts = self.epmc_repo.get_total_citations_count_by_year()
        cumulative = 0
        citations_over_years = []
        for year, year_count in year_counts:
            cumulative += year_count
            citations_over_years.append(
                CitationOverYears(
                    pub_year=int(year),
                    year_count=int(year_count),
                    commulative_count=cumulative,
                )
            )

        return TotalCitations(
            total_citations=cumulative,
            citations_over_years=citations_over_years,
        )
