from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "type": "about:blank",
                "title": "Dados inválidos",
                "status": 422,
                "detail": "A requisição não passou na validação.",
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "type": "about:blank",
                "title": "Erro interno",
                "status": 500,
                "detail": "Ocorreu um erro inesperado.",
                "instance": str(request.url.path),
            },
        )
