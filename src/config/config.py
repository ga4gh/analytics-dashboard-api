import os

from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL",
                                      "postgresql+psycopg://analytics_staging:##R)n\\u0026oN[a2+=}\\u003eNWCNK@analytics-staging.c0q4keadjybw.us-east-2.rds.amazonaws.com:5432/analytics?sslmode=require")

        # Production DB URL — falls back to staging URL so local dev works with one DB.
        # In deployed environments, set PRODUCTION_DATABASE_URL to the production RDS instance.
        self.production_database_url = os.getenv("PRODUCTION_DATABASE_URL", self.database_url)

        self.pubmed_api_key = os.getenv("PUBMED_API_KEY", "")

        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.debug = os.getenv("DEBUG", "False").lower() == "true"

config = Config()
