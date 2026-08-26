from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import escape

from sqlalchemy.orm import Session

from app.application.services.message_templates import get_template, render_template
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


def _event_key(record: RequirementRecord, rule: NotificationRule, recipient: str) -> str:
    from app.application.services.notification import notification_key

    return notification_key(
        record.company_id,
        record.employee_id,
        record.requirement_type_id,
        record.expiry_date,
        rule.code,
        f"EMAIL:{recipient.lower()}",
    )


@dataclass
class QueuedMessage:
    event: NotificationEvent
    company: Company
    employee: Employee
    record: RequirementRecord
    requirement_type: RequirementType
    days: int


class BatchNotificationService:
    """Agrupa avisos por destinatário sem expor dados entre colaboradores."""

    def __init__(self, session: Session, email_gateway):
        self.session = session
        self.email_gateway = email_gateway
        self.repository = SQLAlchemyNotificationRepository(session)
        self.groups: dict[tuple[str, str], list[QueuedMessage]] = defaultdict(list)
        self.counts: Counter[str] = Counter()

    def queue(
        self,
        company: Company,
        employee: Employee,
        record: RequirementRecord,
        requirement_type: RequirementType,
        rule: NotificationRule,
        days: int,
    ) -> None:
        if not self.email_gateway.settings.mail_enabled:
            self.counts["emails_not_configured"] = 1
            return
        recipients = list(company.responsible_emails)
        if self.email_gateway.settings.notify_employee and employee.email:
            recipients.append(employee.email)
        for recipient in dict.fromkeys(item.strip().lower() for item in recipients if item.strip()):
            event, created = self.repository.create_pending(
                NotificationEvent(
                    company_id=company.id,
                    employee_id=employee.id,
                    requirement_record_id=record.id,
                    notification_rule_id=rule.id,
                    expiry_date=record.expiry_date,
                    notification_key=_event_key(record, rule, recipient),
                    channel="EMAIL",
                    destination_masked=mask_email(recipient),
                    status=EventStatus.PENDING,
                )
            )
            if not created and event.status == EventStatus.SENT:
                self.counts["duplicates_skipped"] += 1
                continue
            event.status, event.attempts = EventStatus.SENDING, event.attempts + 1
            self.groups[(str(company.id), recipient)].append(
                QueuedMessage(event, company, employee, record, requirement_type, days)
            )

    def flush(self) -> Counter[str]:
        template = get_template(self.session, "EMAIL")
        for (_, recipient), messages in self.groups.items():
            try:
                text_parts = [self._text(template.body, message) for message in messages]
                subject = self._subject(template.subject, messages)
                text = "\n\n".join(text_parts)
                message_id = self.email_gateway.send(
                    recipients=[recipient],
                    subject=subject,
                    text=text,
                    html="<hr>".join(
                        "<br>".join(escape(line) for line in value.splitlines())
                        for value in text_parts
                    ),
                )
                for queued in messages:
                    queued.event.provider_message_id = message_id
                    queued.event.status = EventStatus.SENT
                    queued.event.sent_at = datetime.now().astimezone()
                    queued.event.error_message = None
                self.counts["emails_sent"] += 1
            except Exception as error:
                for queued in messages:
                    queued.event.status = EventStatus.FAILED
                    queued.event.error_message = str(error)[:500]
                self.counts["errors"] += 1
        self.groups.clear()
        return self.counts

    @staticmethod
    def _text(template: str, message: QueuedMessage) -> str:
        return render_template(
            template,
            {
                "empresa": message.company.name,
                "unidade": message.employee.unit or "-",
                "colaborador": message.employee.full_name,
                "item": message.requirement_type.name,
                "data_vencimento": message.record.expiry_date.strftime("%d/%m/%Y"),
                "dias_restantes": message.days,
                "situacao": message.record.calculated_status,
            },
        )

    @staticmethod
    def _subject(template: str | None, messages: list[QueuedMessage]) -> str:
        if len(messages) == 1:
            return render_template(
                template or "Aviso de vencimento — {item} — {colaborador}",
                {
                    "empresa": messages[0].company.name,
                    "unidade": messages[0].employee.unit or "-",
                    "colaborador": messages[0].employee.full_name,
                    "item": messages[0].requirement_type.name,
                    "data_vencimento": messages[0].record.expiry_date.strftime("%d/%m/%Y"),
                    "dias_restantes": messages[0].days,
                    "situacao": messages[0].record.calculated_status,
                },
            )
        return f"Resumo de vencimentos — {messages[0].company.name} ({len(messages)} avisos)"
