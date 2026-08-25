from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.security import require_api_key
from app.application.dto.schemas import MessageTemplateResponse, MessageTemplateUpdate
from app.application.services.message_templates import DEFAULT_TEMPLATES, get_or_create_templates
from app.infrastructure.database.session import get_session

router = APIRouter(
    prefix="/api/v1/templates", tags=["templates"], dependencies=[Depends(require_api_key)]
)


@router.get("", response_model=list[MessageTemplateResponse])
def list_templates(session: Session = Depends(get_session)):
    templates = get_or_create_templates(session)
    session.commit()
    return templates


@router.put("/{code}", response_model=MessageTemplateResponse)
def update_template(code: str, payload: MessageTemplateUpdate, session: Session = Depends(get_session)):
    normalized = code.upper()
    if normalized not in DEFAULT_TEMPLATES:
        raise HTTPException(404, "Modelo não encontrado")
    templates = {item.code: item for item in get_or_create_templates(session)}
    template = templates[normalized]
    template.subject = payload.subject.strip() if payload.subject else None
    template.body = payload.body.strip()
    template.active = payload.active
    if normalized == "WHATSAPP":
        template.subject = None
    session.commit()
    session.refresh(template)
    return template
