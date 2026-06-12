import logging
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .engine import engine

logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        logger.exception("Session error: %s", e)
        session.rollback()
        raise
    finally:
        session.close()
