from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers.problem_details import install_exception_handlers
from app.api.routes import companies, executions, health
from app.configuration.settings import get_settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Em desenvolvimento facilita a primeira execução; produção usa Alembic.
    if not get_settings().production:
        Base.metadata.create_all(engine)
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.enable_docs and not settings.production else None,
    openapi_url="/openapi.json" if settings.enable_docs and not settings.production else None,
    lifespan=lifespan,
)
install_exception_handlers(app)
app.include_router(health.router)
app.include_router(companies.router)
app.include_router(executions.router)
