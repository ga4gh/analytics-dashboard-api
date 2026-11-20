import logging
import re
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.database import db_settings, production_db_settings
from src.config.session import get_staging_db, get_production_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["Debug"])


def _mask(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def _db_stats(db: Session, url: str) -> dict:
    try:
        articles = db.execute(text("SELECT COUNT(*) FROM pmc_articles")).scalar()
        ingestions = db.execute(text("SELECT COUNT(*) FROM ingestion")).scalar()
        return {
            "status": "connected",
            "url": _mask(url),
            "pmc_articles": articles,
            "ingestion_runs": ingestions,
        }
    except Exception as e:
        return {"status": "error", "url": _mask(url), "detail": str(e)}


@router.get("/db-info")
async def db_info(
    staging_db: Session = Depends(get_staging_db),
    production_db: Session = Depends(get_production_db),
):
    """
    Queries both databases and returns stats side by side.
    Confirms the staging/production split is wired correctly.
    Remove or restrict this endpoint before going to production.
    """
    return {
        "staging": _db_stats(staging_db, db_settings.sqlalchemy_url),
        "production": _db_stats(production_db, production_db_settings.sqlalchemy_url),
    }
