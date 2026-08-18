from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import require_api_key
from app.application.dto.schemas import ExecutionResponse, NotificationResponse
from app.application.services.execution import ExecutionService
from app.configuration.settings import get_settings
from app.domain.enums.core import EventStatus
from app.domain.exceptions.core import ExecutionConflict
from app.infrastructure.database.models import NotificationEvent, SyncExecution
from app.infrastructure.database.session import get_session
from app.infrastructure.email.gateway import SMTPEmailGateway
from app.infrastructure.google_sheets.gateway import GoogleSheetsGateway

router = APIRouter(prefix="/api/v1", tags=["executions"], dependencies=[Depends(require_api_key)])


def service(session: Session) -> ExecutionService:
    settings = get_settings()
    return ExecutionService(session, GoogleSheetsGateway(settings), SMTPEmailGateway(settings))


@router.post("/executions/run", status_code=status.HTTP_202_ACCEPTED)
def run_all(session: Session = Depends(get_session)):
    try:
        return service(session).run_all()
    except ExecutionConflict as error:
        raise HTTPException(409, str(error)) from error


@router.post("/companies/{company_id}/executions/run", status_code=status.HTTP_202_ACCEPTED)
def run_company(company_id: uuid.UUID, session: Session = Depends(get_session)):
    try:
        return service(session).run_company_by_id(company_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ExecutionConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/executions/latest", response_model=ExecutionResponse)
def latest(session: Session = Depends(get_session)):
    execution = session.scalar(select(SyncExecution).order_by(SyncExecution.started_at.desc()))
    if not execution:
        raise HTTPException(404, "Nenhuma execução encontrada")
    return execution


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: uuid.UUID, session: Session = Depends(get_session)):
    execution = session.get(SyncExecution, execution_id)
    if not execution:
        raise HTTPException(404, "Execução não encontrada")
    return execution


@router.post("/notifications/{notification_id}/retry", response_model=NotificationResponse)
def retry_notification(notification_id: uuid.UUID, session: Session = Depends(get_session)):
    event = session.get(NotificationEvent, notification_id)
    if not event:
        raise HTTPException(404, "Notificação não encontrada")
    if event.status == EventStatus.SENT:
        raise HTTPException(422, "Notificação já enviada")
    event.status = EventStatus.PENDING
    session.commit()
    return event
