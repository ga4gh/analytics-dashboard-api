import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

from pydantic import version

from src.models.entities.pmc_article import PMCArticle
from src.models.entities.pmc_author import PMCAuthor, PMCAffiliation, ArticleAuthor
from src.models.entities.extras import FullText, Grant
from src.models.entities.citations import Citation, Reference
from src.models.entities.record import Record, RecordType, Source, Status, ProductType
from src.models.entities.ingestion import Ingestion

import requests
import pandas as pd
from pathlib import Path
import os
import xmltodict


class EPMCClient:
    def __init__(self) -> None:
        self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
        self.grants_url = "https://www.ebi.ac.uk/europepmc/GristAPI/rest/"
        self.token = ""

    def create_article(self, article_data, record_id, ingestion_id: int, created_by: str = "system", cited_by: int = 0) -> PMCArticle:
        return PMCArticle(
            id=None,
            record_id=record_id,
            ingestion_id=ingestion_id,
            source=article_data.get("source", ""),
            epmc_id=article_data.get("id"),
            pm_id=article_data.get("id"),
            pmc_id=article_data.get("pmcid", "") or "",
            full_text_id=((article_data.get("fullTextIdList") or {}).get("fullTextId") or ""),
            doi=article_data.get("doi", "") or "",
            title=article_data.get("title", "") or "",
            pub_year=int(article_data.get("pubYear") or 0),
            abstract_text=article_data.get("abstractText", "") or "",
            affiliation=article_data.get("affiliation", "") or "",
            publication_status=article_data.get("publicationStatus", "") or "",
            language=article_data.get("language", "") or "",
            pub_type=((article_data.get("pubTypeList") or {}).get("pubType") or None),
            is_open_access=article_data.get("isOpenAccess"),
            inepmc=article_data.get("inEPMC"),  
            inpmc=article_data.get("inPMC"),    
            has_pdf=article_data.get("hasPDF"),
            has_book=article_data.get("hasBook"),
            has_suppl=article_data.get("hasSuppl"),
            cited_by_count=int(cited_by),
            has_references=article_data.get("hasReferences"),
            date_of_creation=_parse_dt(article_data.get("dateOfCreation")),
            first_index_date=_parse_dt(article_data.get("firstIndexDate")),
            fulltext_receive_date=_parse_dt(article_data.get("fullTextReceivedDate")),
            revision_date=_parse_dt(article_data.get("dateOfRevision")),
            epub_date=_parse_dt(article_data.get("electronicPublicationDate")),
            first_publication_date=_parse_dt(article_data.get("firstPublicationDate")),
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_author(self, author_data, ingestion_id: int, created_by: str = "system") -> PMCAuthor:
        author_order = int(author_data.get("authorOrder") or 0)
        return PMCAuthor(
            id=None,
            ingestion_id=ingestion_id,
            fullname=author_data.get("fullName", "") or "",
            firstname=author_data.get("firstName"),
            lastname=author_data.get("lastName"),
            initials=author_data.get("initials"),
            orcid=(author_data.get("authorId") or {}).get("value"),
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_article_author(
        self,
        article_id: int,
        author_id: int,
        author_order: int,
        ingestion_id: int,
        created_by: str = "system",
    ) -> ArticleAuthor:
        return ArticleAuthor(
            id=None,
            ingestion_id=ingestion_id,
            article_id=article_id,
            author_id=author_id,
            author_order=author_order,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_affiliation(
        self,
        affiliation_data,
        author_id: int,
        article_id: int,
        affiliation_order: int,
        ingestion_id: int,
        created_by: str = "system",
    ) -> PMCAffiliation:
        org_name = affiliation_data.get("affiliation") if isinstance(affiliation_data, dict) else affiliation_data
        return PMCAffiliation(
            id=None,
            ingestion_id=ingestion_id,
            author_id=author_id,
            article_id=article_id,
            org_name=org_name,
            affiliation_order=affiliation_order,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_grant(self, article_data, record_id: int, ingestion_id: int, created_by: str = "system") -> Grant:
        return Grant(
            id=None,
            ingestion_id=ingestion_id,
            record_id=record_id,
            grant_id=article_data.get("grantId") or article_data.get("grant_id"),
            agency=article_data.get("agency"),
            family_name=None,
            given_name=None,
            orcid=None,
            funder_name=None,
            doi=None,
            title=None,
            abstract=None,
            start_date=_parse_dt(article_data.get("startDate")),
            end_date=_parse_dt(article_data.get("endDate")),
            institution_name=None,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_citation(self, cite, article_id: int, ingestion_id: int, created_by: str = "system") -> Citation:

        return Citation(
            id=None,
            ingestion_id=ingestion_id,
            article_id=article_id,
            citation_id=str(cite.get("id")) if cite.get("id") is not None else None,
            source=cite.get("source"),
            citation_type=cite.get("citationType") or cite.get("citation_type"),
            title=cite.get("title"),
            authors=cite.get("authorString"),
            pub_year=int(cite.get("pubYear") or cite.get("pub_year") or 0),
            citation_count=cite.get("citedByCount"),
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_reference(self, ref, article_id: int, ingestion_id: int, created_by: str = "system") -> Reference:
        return Reference(
            id=None,
            ingestion_id=ingestion_id,
            article_id=article_id,
            reference_id=str(ref.get("id")) if ref.get("id") is not None else None,
            source=ref.get("source"),
            citation_type=ref.get("citationType") or ref.get("citation_type"),
            title=ref.get("title"),
            authors=ref.get("authorString"),
            pub_year=int(ref.get("pubYear") or ref.get("pub_year") or 0),
            issn=ref.get("ISSN") or ref.get("issn"),
            essn=ref.get("ESSN") or ref.get("essn"),
            cited_order=int(ref.get("citedOrder") or ref.get("cited_order") or 0),
            match=ref.get("match") if ref.get("match") is not None else False,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_grant_api(self, gr, record_id: int, ingestion_id: int, created_by: str = "system") -> Grant:
        person = gr.get("Person") or {}
        grant_info = gr.get("Grant") or {}
        institution = gr.get("Institution") or {}
        funder = grant_info.get("Funder") or {}

        person_aliases = person.get("Alias") or []
        if isinstance(person_aliases, dict):
            person_aliases = [person_aliases]
        
        orcid = ""
        for alias in person_aliases:
            if alias.get("Source") == "ORCID":
                orcid = alias.get("value") or ""
                break

        return Grant(
            id=None,
            ingestion_id=ingestion_id,
            record_id=record_id,
            grant_id=grant_info.get("Id"),
            agency=funder.get("Name"),
            family_name=person.get("FamilyName"),
            given_name=person.get("GivenName"),
            alias=person_aliases,
            initials=person.get("Initials"),
            orcid=orcid or None,
            funder_name=funder.get("Name"),
            doi=grant_info.get("Doi"),
            title=grant_info.get("Title"),
            abstract=grant_info.get("Abstract"),
            start_date=_parse_dt(grant_info.get("StartDate")),
            end_date=_parse_dt(grant_info.get("EndDate")),
            institution_name=institution.get("Name"),
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_fulltext(self, article_id: int, ft, ingestion_id: int, created_by: str = "system") -> FullText:
        return FullText(
            id=None,
            ingestion_id=ingestion_id,
            article_id=article_id,
            availability=ft.get("availability"),
            availability_code=ft.get("availabilityCode"),
            document_style=ft.get("documentStyle"),
            site=ft.get("site"),
            url=ft.get("url"),
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow(),
            deleted_by=None,
            deleted_at=None,
            version=1,
        )

    def create_record(self, type: str, keyword: str) -> Record:
        return Record(
            id=None,
            record_type=RecordType.Article if type == "ARTICLE" else RecordType.Grant,
            source=Source.Europe_PMC,
            status=Status.Approved,
            keyword=[keyword],
            product_line=ProductType.implementation,
            created_by="system",
            updated_by="system",
            version=1,
        )
    

    def create_ingestion(
        self,
        version,
        keyword: Optional[str] = None,
        run_type: str = "full",
        api_version: Optional[str] = None,
        created_by: str = "system",
    ) -> Ingestion:
        return Ingestion(
            id=None,
            ingested_at=datetime.utcnow(),
            keyword=keyword,
            run_type=run_type,
            api_version=api_version,
            created_by=created_by,
            created_at=datetime.utcnow(),
            version=version,
        )

    def update_ingestion(self, ingestion_id, rows_count: int) -> Ingestion:
        return Ingestion(
            id=ingestion_id,
            rows_count=rows_count,
        )

    def get_articles(self, keyword: str) -> Dict[str, Any]:
        endpoint = self.get_articles_endpoint(keyword)
        logger.info("EPMC full pull: %s%s", self.base_url, endpoint)
        return self.get_json(self.base_url, endpoint, per_page=1000)

    def get_delta_articles(self, keyword: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """Fetch only articles updated between from_date and to_date (YYYY-MM-DD)."""
        endpoint = self.get_delta_articles_endpoint(keyword, from_date, to_date)
        logger.info("EPMC delta pull: %s%s", self.base_url, endpoint)
        return self.get_json(self.base_url, endpoint, per_page=1000)

    def get_references(self, id, source="MED"):
        json_response = self.get_json(self.base_url, self.get_references_endpoint(id, source=source))
        return json_response

    def get_citations(self, pmcid, source="MED"):
        json_response = self.get_json(self.base_url, self.get_citations_endpoint(pmcid, source=source))
        return json_response

    def get_grants(self, keyword):
        json_response = self.get_json(self.grants_url, self.get_grants_endpoint(keyword))
        return json_response

    def get_articles_endpoint(self, keyword: str) -> str:
        return f"search?query={quote(keyword)}&format=json&resultType=core"

    def get_delta_articles_endpoint(self, keyword: str, from_date: str, to_date: str) -> str:
        """Build the UPDATE_DATE-filtered search URL for delta pulls."""
        full_query = f"({keyword}) AND UPDATE_DATE:[{from_date} TO {to_date}]"
        return f"search?query={quote(full_query)}&format=json&resultType=core"

    def get_citations_endpoint(self, id, source="MED"):
        return f"{source}/{id}/citations?format=json"

    def get_references_endpoint(self, id, source="MED"):
        return f"{source}/{id}/references?format=json"

    def get_grants_endpoint(self, keyword):
        return f"get/query='{keyword}'&resultType=core&format=json"

    def get_json(self, base_url: str, endpoint: str, token: Optional[str] = None, per_page: int = 100) -> Dict[str, Any]:
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"

        is_citations_endpoint = "/citations?" in endpoint
        page = 1

        # Citations endpoint uses page-based pagination; others use cursor-based pagination.
        if is_citations_endpoint:
            params = {"pageSize": per_page, "page": page}
        else:
            params = {"pageSize": per_page, "cursorMark": "*"}

        items: List[Dict[str, Any]] = []
        url = base_url + endpoint

        wrapper_key = "resultList"
        inner_key = "result"

        # Safety: avoid infinite loops by counting iterations
        max_iters = 1000
        iters = 0
        top_hit_count = None  # Capture hitCount from first page

        while True:
            if iters >= max_iters:
                break
            iters += 1

            if iters == 1:
                logger.debug("EPMC request: GET %s params=%s", url, params)

            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()

            try:
                data = resp.json()
            except ValueError:
                data = xmltodict.parse(resp.text)

            # Capture hitCount from first page only
            if top_hit_count is None:
                top_hit_count = data.get("hitCount")

            # Detect which wrapper/inner keys contain list items
            page_items = (data.get("resultList") or {}).get("result")
            if page_items:
                wrapper_key, inner_key = "resultList", "result"

            if not page_items:
                page_items = (data.get("citationList") or {}).get("citation")
                if page_items:
                    wrapper_key, inner_key = "citationList", "citation"

            if not page_items:
                page_items = (data.get("referenceList") or {}).get("reference")
                if page_items:
                    wrapper_key, inner_key = "referenceList", "reference"

            if not page_items:
                page_items = (data.get("RecordList") or {}).get("Record")
                if page_items:
                    wrapper_key, inner_key = "RecordList", "Record"

            page_items = page_items or []

            if isinstance(page_items, dict):
                page_items = [page_items]

            items.extend(page_items)

            # Prefer explicit next-page URL if provided
            next_page_url = data.get("nextPageUrl")
            if next_page_url and page_items:
                url = next_page_url
                params = None
                continue

            # Some endpoints return a cursor-like marker for subsequent pages
            next_cursor = data.get("nextCursorMark") or data.get("nextCursor")
            if next_cursor:
                params = {"pageSize": per_page, "cursorMark": next_cursor}
                continue

            # Fallback: use hitCount pagination when available
            hit_count = None
            try:
                hit_count = int(data.get("hitCount") or (data.get(wrapper_key) or {}).get("hitCount"))
            except Exception:
                hit_count = None

            if hit_count is not None:
                # If we've fetched fewer items than hit_count, advance to next page.
                if len(items) < hit_count:
                    if is_citations_endpoint:
                        page += 1
                        params = {"pageSize": per_page, "page": page}
                    else:
                        # Preserve existing fallback for non-citation endpoints.
                        next_offset = max(len(items), per_page)
                        params = {"pageSize": per_page, "offSet": next_offset}
                    continue

            # No further pages detected
            break

        # Build return dict with items and hitCount at same level
        result = {wrapper_key: {inner_key: items}}
        if top_hit_count is not None:
            result["hitCount"] = top_hit_count
        return result


    def write_df_to_csv(self, df: pd.DataFrame, filename: str) -> Path:

        path = Path(filename)
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(path)
        logger.debug("Wrote CSV: %s", path)
        return path


def _parse_dt(value: Optional[str]) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return datetime.utcnow()