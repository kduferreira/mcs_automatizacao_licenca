from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.configuration.settings import get_settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().manual_run_api_key.get_secret_value()
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key ausente ou inválida"
        )
