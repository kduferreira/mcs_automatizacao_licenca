from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import MessageTemplate

DEFAULT_TEMPLATES = {
    "EMAIL": {
        "channel": "EMAIL",
        "subject": "Aviso de vencimento — {item} — {colaborador}",
        "body": "Olá, {colaborador}.\n\nO item {item} da empresa {empresa} vence em {data_vencimento}.\nSituação: {situacao}. Dias restantes: {dias_restantes}.",
    },
    "WHATSAPP": {
        "channel": "WHATSAPP",
        "subject": None,
        "body": "Olá, {colaborador}. O item {item} vence em {data_vencimento}. Situação: {situacao}.",
    },
}


def get_or_create_templates(session: Session) -> list[MessageTemplate]:
    current = {item.code: item for item in session.scalars(select(MessageTemplate))}
    for code, values in DEFAULT_TEMPLATES.items():
        if code not in current:
            current[code] = MessageTemplate(code=code, **values)
            session.add(current[code])
    session.flush()
    return [current[code] for code in DEFAULT_TEMPLATES]


def get_template(session: Session, code: str) -> MessageTemplate:
    return next(item for item in get_or_create_templates(session) if item.code == code)


def render_template(value: str | None, context: dict[str, object]) -> str:
    rendered = value or ""
    for key, item in context.items():
        rendered = rendered.replace("{" + key + "}", str(item))
    return rendered
