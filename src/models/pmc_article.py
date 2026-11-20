from __future__ import annotations

from datetime import datetime
from typing import List, Optional



from pydantic import BaseModel, Field, ConfigDict, field_validator


class PMCFullText(BaseModel):
    id: Optional[int] = None
    article_id: Optional[int] = None
    availability: str
    availability_code: str
    document_style: str
    site: str
    url: str

    model_config = ConfigDict(from_attributes=True)


class PMCCitation(BaseModel):
    id: Optional[int] = None
    article_id: Optional[int] = None
    citation_id: Optional[str] = None  
    source: Optional[str] = None
    citation_type: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    pub_year: Optional[int] = None
    citation_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class PMCReference(BaseModel):
    id: Optional[int] = None
    article_id: Optional[int] = None
    reference_id: Optional[str] = None  
    source: Optional[str] = None
    citation_type: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    pub_year: Optional[int] = None
    issn: Optional[str] = None
    essn: Optional[str] = None
    cited_order: Optional[int] = None
    match: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class Keyword(BaseModel):
    id: Optional[int] = None
    article_id: int
    value: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class Grant(BaseModel):
    id: Optional[int] = None
    record_id: int
    grant_id: Optional[str] = None
    agency: Optional[str] = None

    family_name: Optional[str] = None
    given_name: Optional[str] = None
    initial: Optional[str] = None
    alias: Optional[List[str]] = None
    orcid: Optional[str] = None

    funder_name: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    institution_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class PMCAffiliation(BaseModel):
    id: Optional[int] = None
    author_id: int
    article_id: int
    org_name: Optional[str] = None
    affiliation_order: int

    model_config = ConfigDict(from_attributes=True)


class PMCAuthor(BaseModel):
    id: Optional[int] = None
    fullname: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    initials: Optional[str] = None
    orcid: Optional[str] = None
    author_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class PMCArticle(BaseModel):

    id: Optional[int] = None
    record_id: int

    source: str
    pm_id: Optional[str] = None
    pmc_id: str
    full_text_id: str
    doi: str
    title: str
    pub_year: int
    abstract_text: str
    affiliation: str
    publication_status: str  
    language: str
    pub_type: Optional[str] = None

    @field_validator("pub_type", mode="before")
    @classmethod
    def coerce_pub_type(cls, v):
        if isinstance(v, list):
            return v[0] if v else None
        return v

    is_open_access: bool = False
    inepmc: bool = False
    inpmc: bool = False
    has_pdf: bool = False
    has_book: bool = False
    has_suppl: bool = False

    cited_by_count: int = 0
    has_references: bool = False

    date_of_creation: Optional[datetime] = None
    first_index_date: Optional[datetime] = None
    fulltext_receive_date: Optional[datetime] = None
    revision_date: Optional[datetime] = None
    epub_date: Optional[datetime] = None
    first_publication_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PMCArticleFull(PMCArticle):
    authors: List[PMCAuthor] = Field(default_factory=list)
    affiliations: List[PMCAffiliation] = Field(default_factory=list)
    grants: List[Grant] = Field(default_factory=list)
    fulltexts: List[PMCFullText] = Field(default_factory=list)
    citations: List[PMCCitation] = Field(default_factory=list)
    references: List[PMCReference] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class PMCArticleCustom(PMCArticle):
    authors: List[PMCAuthor] = Field(default_factory=list)
    affiliations: List[PMCAffiliation] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PMCArticleListResponse(BaseModel):
    """Response model for all-articles endpoint with article count and list."""
    article_count: int
    articles: List[PMCArticleFull]

    model_config = ConfigDict(from_attributes=True)
    
class PMCArticleListCustomResponse(BaseModel):
    """Response model for all-articles endpoint with article count and list."""
    article_count: int
    articles: List[PMCArticleCustom]

    model_config = ConfigDict(from_attributes=True)