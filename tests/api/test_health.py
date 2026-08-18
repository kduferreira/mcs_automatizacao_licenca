from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.dependencies.security import require_api_key
from app.api.routes.health import health


def test_health():
    with Session(create_engine("sqlite://")) as session:
        assert health(session) == {"status": "ok"}


def test_admin_endpoint_requires_key():
    try:
        require_api_key(None)
    except HTTPException as error:
        assert error.status_code == 401
    else:
        raise AssertionError("A API key deveria ser obrigatória")
