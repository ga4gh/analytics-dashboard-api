from .config import config as app_config


class DatabaseSettings:
    """
    Staging database settings.
    Reads DATABASE_URL from environment via config.py.
    Used by the ingestion pipeline and /staging/* endpoints.
    """

    @property
    def sqlalchemy_url(self) -> str:
        return app_config.database_url


class ProductionDatabaseSettings:
    """
    Production database settings.
    Reads PRODUCTION_DATABASE_URL from environment via config.py.
    Falls back to staging URL when PRODUCTION_DATABASE_URL is not set —
    safe for local dev where both DBs are the same instance.
    """

    @property
    def sqlalchemy_url(self) -> str:
        return app_config.production_database_url


db_settings = DatabaseSettings()
production_db_settings = ProductionDatabaseSettings()
