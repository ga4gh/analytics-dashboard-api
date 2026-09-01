import logging
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .engine import staging_engine, production_engine

logger = logging.getLogger(__name__)

StagingSessionLocal = sessionmaker(
    bind=staging_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

ProductionSessionLocal = sessionmaker(
    bind=production_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_staging_db() -> Generator[Session, None, None]:
    """FastAPI dependency for the staging database (ingestion pipeline, /staging/* endpoints)."""
    session = StagingSessionLocal()
    try:
        yield session
    except Exception as e:
        logger.exception("Staging session error: %s", e)
        session.rollback()
        raise
    finally:
        session.close()


def get_production_db() -> Generator[Session, None, None]:
    """FastAPI dependency for the production database (dashboard, KPI, chart endpoints)."""
    session = ProductionSessionLocal()
    try:
        yield session
    except Exception as e:
        logger.exception("Production session error: %s", e)
        session.rollback()
        raise
    finally:
        session.close()


# Backward-compat alias — existing routers that import get_session continue to work.
# They are dashboard read endpoints so they get the production session.
get_session = get_production_db
