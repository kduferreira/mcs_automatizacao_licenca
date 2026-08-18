from __future__ import annotations

import hashlib
from datetime import datetime

from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy.orm import Session

from app.domain.enums.core import EventStatus
from app.domain.rules.normalization import mask_email
from app.infrastructure.database.models import (
    Company,
    Employee,
    NotificationEvent,
    NotificationRule,
    RequirementRecord,
    RequirementType,
)
from app.repositories.sqlalchemy import SQLAlchemyNotificationRepository


def notification_key(
    company_id: object,
    employee_id: object,
    requirement_type_id: object,
    expiry_date: object,
    rule_code: str,
    channel: str,
) -> str:
    value = "|".join(
        map(str, [company_id, employee_id, requirement_type_id, expiry_date, rule_code, channel])
    )
    return hashlib.sha256(value.encode()).hexdigest()


class NotificationService:
    def __init__(self, session: Session, email_gateway):
        self.session, self.email_gateway = session, email_gateway
        self.repository = SQLAlchemyNotificationRepository(session)
        self.templates = Environment(
            loader=PackageLoader("app", "templates"), autoescape=select_autoescape()
        )

    def notify(
        self,
        company: Company,
        employee: Employee,
        record: RequirementRecord,
        requirement_type: RequirementType,
        rule: NotificationRule,
        days: int,
    ) -> str:
        key = notification_key(
            company.id, employee.id, requirement_type.id, record.expiry_date, rule.code, "EMAIL"
        )
        event, created = self.repository.create_pending(
            NotificationEvent(
                company_id=company.id,
                employee_id=employee.id,
                requirement_record_id=record.id,
                notification_rule_id=rule.id,
                expiry_date=record.expiry_date,
                notification_key=key,
                channel="EMAIL",
                destination_masked=", ".join(
                    filter(None, map(mask_email, company.responsible_emails))
                ),
                status=EventStatus.PENDING,
            )
        )
        if not created and event.status == EventStatus.SENT:
            return "DUPLICADO"
        event.status, event.attempts = EventStatus.SENDING, event.attempts + 1
        context = {
            "empresa": company.name,
            "unidade": employee.unit or "-",
            "colaborador": employee.full_name,
            "item": requirement_type.name,
            "data_vencimento": record.expiry_date.strftime("%d/%m/%Y"),
            "dias_restantes": days,
            "situacao": record.calculated_status,
        }
        try:
            subject = f"⚠ Aviso de vencimento — {requirement_type.name} — {employee.full_name}"
            if days == 3:
                subject = "🔴 Alerta urgente — vencimento em 3 dias"
            elif days == 1:
                subject = "🚨 Alerta crítico — vencimento amanhã"
            elif days == 0:
                subject = f"🚨 Vencimento hoje — {requirement_type.name} — {employee.full_name}"
            elif days < 0:
                subject = f"🔴 Item vencido — {requirement_type.name} — {employee.full_name}"
            template = self.templates.get_template("notification.html")
            text = self.templates.get_template("notification.txt").render(**context)
            event.provider_message_id = self.email_gateway.send(
                recipients=company.responsible_emails,
                subject=subject,
                text=text,
                html=template.render(**context),
            )
            event.status, event.sent_at, event.error_message = (
                EventStatus.SENT,
                datetime.now().astimezone(),
                None,
            )
            return "ENVIADO"
        except Exception as error:
            event.status, event.error_message = EventStatus.FAILED, str(error)[:500]
            return "FALHOU"
