import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.session import get_staging_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/staging", tags=["Staging / Curation"])


@router.get("/health")
async def staging_health(db: Session = Depends(get_staging_db)):
    """Confirm the staging DB session is reachable."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "staging"}
    except Exception as e:
        logger.exception("Staging DB health check failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/info")
async def staging_info(db: Session = Depends(get_staging_db)):
    """Staging DB stats — only touches the staging database."""
    try:
        articles = db.execute(text("SELECT COUNT(*) FROM pmc_articles")).scalar()
        ingestions = db.execute(text("SELECT COUNT(*) FROM ingestion")).scalar()
        return {
            "database": "staging",
            "pmc_articles": articles,
            "ingestion_runs": ingestions,
        }
    except Exception as e:
        logger.exception("Staging info query failed: %s", e)
        return {"status": "error", "detail": str(e)}
