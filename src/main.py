import os
import logging
import os

import uvicorn
from fastapi import FastAPI
from sqlalchemy.engine import make_url
from urllib.parse import quote
from sqlalchemy.engine import make_url
from urllib.parse import quote

# config
from .config.constants import GH_BASE_URL

# clients / repos / services / routers
from .clients.github import GithubRepoClient
from .config import constants
from .config.config import config
from .config.constants import GH_BASE_URL
from .models.github import GithubRepo
from .models.pypi import Pypi as PypiModel
from .models.record import Record
from .repositories import setup, sqlbuilder
from .repositories.github import GithubRepo as GithubRepoRepository
from .repositories.pypi import Pypi as PypiRepo
from .repositories.record import Record as RecordRepo
from .routers.epmc import EPMC as EPMCRouter
from .routers.github import GithubRepoRouter
from .routers.health import router as health_router
from .routers.pypi import Pypi as PypiRouter
from .routers.summary import router as summary_router
from .services.github import GithubRepos as GithubReposService
from .services.pypi import Pypi as PypiService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main() -> FastAPI:
    app = FastAPI()

    # DB setup
    try:
        sa_url = make_url(config.database_url)
        user = quote(sa_url.username or "", safe="")
        pwd = quote(sa_url.password or "", safe="")
        host = sa_url.host or ""
        port = sa_url.port or ""
        dbname = sa_url.database or ""
        dsn = f"postgresql://{user}:{pwd}@{host}:{port}/{dbname}"
    except Exception:
        # Fallback: pass the original URL through (may work if already libpq-compatible)
        dsn = config.database_url

    db_conn = setup.DatabaseConnection(dsn)
    db_conn.connect()

    logger.info("Database connected via SQLAlchemy ORM")                     

    # Fields setup
    record_fields = set(Record.model_fields.keys())
    record_sql_builder = sqlbuilder.SQLBuilder("records").allow_fields(record_fields - {"id"})
    record_repo = RecordRepo(db_conn, record_sql_builder)

    # GitHub setup
    gh_api_key = os.getenv("GITHUB_API_KEY", "")
    gh_org = os.getenv("GITHUB_ORG", "ga4gh")  # change via env if needed
    gh_client = GithubRepoClient(GH_BASE_URL, gh_api_key)
    gh_repo_fields = set(GithubRepo.model_fields.keys())
    gh_repo_sql_builder = sqlbuilder.SQLBuilder("github_repos").allow_fields(gh_repo_fields - {"id"})
    gh_repo = GithubRepoRepository(db_conn, gh_repo_sql_builder)
    gh_service = GithubReposService(gh_repo, gh_client, record_repo)
    gh_router = GithubRepoRouter(gh_service)

    # PyPi setup
    pypi_fields = set(PypiModel.model_fields.keys())
    pypi_sql_builder = sqlbuilder.SQLBuilder("pypi").allow_fields(pypi_fields)
    pypi_repo = PypiRepo(db_conn, pypi_sql_builder)
    pypi_service = PypiService(pypi_repo)
    pypi_router = PypiRouter(pypi_service)

    # EPMC setup
    epmc_router = EPMCRouter()

    # --- FastAPI app + router
    app.include_router(gh_router.router)
    app.include_router(pypi_router.router)
    app.include_router(epmc_router.router)
    app.include_router(health_router)
    app.include_router(summary_router)

    return app

if __name__ == "__main__":
    app = main()
    uvicorn.run(app, host=config.host, port=config.port, reload=False)
