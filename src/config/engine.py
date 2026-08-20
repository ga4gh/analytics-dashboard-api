from sqlalchemy import create_engine
from importlib import util
from src.config.database import db_settings, production_db_settings


def _resolve_url(raw_url: str) -> str:
    """Ensure the URL has an installed DBAPI driver specifier."""
    if raw_url.startswith("postgresql://"):
        if util.find_spec("psycopg"):
            return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif util.find_spec("psycopg2"):
            return raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return raw_url


staging_engine = create_engine(
    _resolve_url(db_settings.sqlalchemy_url),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

production_engine = create_engine(
    _resolve_url(production_db_settings.sqlalchemy_url),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Backward-compat alias — existing code that imports `engine` continues to work.
engine = staging_engine
