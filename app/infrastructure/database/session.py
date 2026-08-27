from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.configuration.settings import get_settings


def build_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql+psycopg://") and ".pooler.supabase.com" in url:
        # O pool de transações do Supabase pode alternar a sessão PostgreSQL
        # por trás da mesma conexão. Prepared statements do Psycopg não são
        # seguros nesse cenário e provocam DuplicatePreparedStatement.
        options["connect_args"] = {"prepare_threshold": None}
    return create_engine(url, **options)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
