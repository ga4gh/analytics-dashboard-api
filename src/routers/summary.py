from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config.session import get_session

router = APIRouter(tags=["Summary"])


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d") if dt else None


@router.get("/summary/overview")
async def get_overview(db: Session = Depends(get_session)):
    """
    Returns record count and last ingestion timestamp for each data source.
    Used by the GA4GH Community persona data freshness panel.
    """
    epmc = db.execute(text("""
        SELECT
            COUNT(DISTINCT a.pm_id)      AS count,
            MAX(i.ingested_at)           AS last_ingested
        FROM pmc_articles a
        LEFT JOIN ingestion i ON a.ingestion_id = i.id
        WHERE a.pm_id IS NOT NULL
    """)).fetchone()

    github = db.execute(text("""
        SELECT
            COUNT(*)          AS count,
            MAX(updated_at)   AS last_ingested
        FROM github_repos
    """)).fetchone()

    pypi = db.execute(text("""
        SELECT
            COUNT(DISTINCT project_name)  AS count,
            MAX(updated_at)               AS last_ingested
        FROM pypi
    """)).fetchone()

    return {
        "epmc":   {"count": int(epmc.count or 0),   "last_ingested": _fmt(epmc.last_ingested)},
        "github": {"count": int(github.count or 0), "last_ingested": _fmt(github.last_ingested)},
        "pypi":   {"count": int(pypi.count or 0),   "last_ingested": _fmt(pypi.last_ingested)},
    }
