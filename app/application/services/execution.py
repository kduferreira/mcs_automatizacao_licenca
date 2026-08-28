from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.batch_notifications import BatchNotificationService
from app.application.services.notification import notification_key
from app.application.services.sheet_mapper import SheetMapper
from app.domain.enums.core import CalculatedStatus, EventStatus, ExecutionStatus
from app.domain.exceptions.core import ExecutionConflict
from app.domain.rules.expiration import ExpirationPolicy
from app.domain.rules.normalization import normalize_header, parse_sheet_date
from app.infrastructure.database.models import (
    Company,
    Employee,
    NotificationEvent,
    NotificationRule,
    RequirementRecord,
    RequirementType,
    SyncExecution,
)
from app.repositories.sqlalchemy import (
    SQLAlchemyCompanyRepository,
    SQLAlchemyEmployeeRepository,
    SQLAlchemyExecutionRepository,
    SQLAlchemyNotificationRepository,
    SQLAlchemyRequirementRepository,
)

logger = logging.getLogger(__name__)

HISTORY_HEADERS = [
    "ID_EVENTO",
    "ID_EXECUCAO",
    "EMPRESA",
    "ID_AUTOMACAO",
    "COLABORADOR",
    "ITEM",
    "DATA_VENCIMENTO",
    "DIAS_RESTANTES",
    "TIPO_AVISO",
    "SEVERIDADE",
    "CANAL",
    "DESTINATARIO_MASCARADO",
    "DATA_ENVIO",
    "RESULTADO",
    "ID_MENSAGEM_PROVEDOR",
    "DETALHE_ERRO",
    "CHAVE_NOTIFICACAO",
]
EXECUTION_HEADERS = [
    "ID_EXECUCAO",
    "EMPRESA",
    "INICIO",
    "FIM",
    "STATUS",
    "LINHAS_LIDAS",
    "EMPREGADOS_PROCESSADOS",
    "ITENS_PROCESSADOS",
    "VALIDOS",
    "EM_ALERTA",
    "VENCENDO_HOJE",
    "VENCIDOS",
    "EMAILS_ENVIADOS",
    "DUPLICADOS_IGNORADOS",
    "ERROS",
]


class ExecutionService:
    def __init__(self, session: Session, sheets, email, today: date | None = None, telegram=None):
        self.session, self.sheets, self.email = session, sheets, email
        self.today = today or date.today()
        self.telegram = telegram

    def run_all(self, trigger_type: str = "MANUAL") -> dict:
        executions = SQLAlchemyExecutionRepository(self.session)
        if executions.running_for(None):
            raise ExecutionConflict("Já existe uma execução global ativa.")
        root = SyncExecution(status=ExecutionStatus.RUNNING, trigger_type=trigger_type)
        self.session.add(root)
        self.session.commit()
        results = []
        for company in SQLAlchemyCompanyRepository(self.session).active():
            try:
                result = self.run_company(company, trigger_type, root.id)
                result["telegram"] = self._send_telegram_summary(company, result, trigger_type)
                results.append(result)
            except Exception as error:
                self.session.rollback()
                results.append(
                    {
                        "company_code": company.code,
                        "status": "FAILED",
                        "errors": 1,
                        "detail": str(error)[:200],
                    }
                )
        failed = sum(item["status"] == "FAILED" for item in results)
        root.finished_at = datetime.now().astimezone()
        root.status = (
            ExecutionStatus.FAILED
            if failed == len(results)
            else (ExecutionStatus.PARTIAL_SUCCESS if failed else ExecutionStatus.SUCCESS)
        )
        root.summary = self._summary(root, results)
        root.summary["telegram"] = {
            item["company_code"]: item.get("telegram", "FALHOU") for item in results
        }
        self.session.commit()
        return root.summary

    def run_company_by_id(self, company_id: uuid.UUID, trigger_type: str = "MANUAL") -> dict:
        company = SQLAlchemyCompanyRepository(self.session).get(company_id)
        if not company:
            raise LookupError("Empresa não encontrada")
        if SQLAlchemyExecutionRepository(self.session).running_for(company.id):
            raise ExecutionConflict("Já existe uma execução ativa para esta empresa.")
        result = self.run_company(company, trigger_type)
        result["telegram"] = self._send_telegram_summary(company, result, trigger_type)
        return result

    def run_company(
        self, company: Company, trigger_type: str, parent_id: uuid.UUID | None = None
    ) -> dict:
        if company.spreadsheet_id.startswith("LOCAL_UPLOAD:"):
            return self._run_local_company(company, trigger_type)

        execution = SyncExecution(
            company_id=company.id, status=ExecutionStatus.RUNNING, trigger_type=trigger_type
        )
        self.session.add(execution)
        self.session.commit()
        counts: Counter[str] = Counter()
        telegram_items: list[dict[str, object]] = []
        try:
            values = self.sheets.read_main_sheet(company)
            mapper = SheetMapper(values)
            mapper.require("NOME COMPLETO")
            types = list(
                self.session.scalars(
                    select(RequirementType).where(RequirementType.active.is_(True))
                )
            )
            types_by_header = {
                normalize_header(item.spreadsheet_header or ""): item
                for item in types
                if item.spreadsheet_header
            }
            rules = {
                rule.days_before_expiry: rule
                for rule in self.session.scalars(
                    select(NotificationRule).where(
                        NotificationRule.enabled.is_(True), NotificationRule.send_email.is_(True)
                    )
                )
            }
            employee_repo, requirement_repo = (
                SQLAlchemyEmployeeRepository(self.session),
                SQLAlchemyRequirementRepository(self.session),
            )
            notification = BatchNotificationService(self.session, self.email)
            telegram_notifications = SQLAlchemyNotificationRepository(self.session)
            telegram_items = []
            update_values = []
            for row in mapper.mapped_rows():
                counts["rows_read"] += 1
                try:
                    name = str(row.values.get("NOME_COMPLETO") or "").strip()
                    if not name:
                        raise ValueError("nome obrigatório")
                    employee = employee_repo.upsert(
                        company.id,
                        row.automation_id,
                        full_name=name,
                        unit=self._text(row.values.get("UNIDADE")),
                        email=self._text(row.values.get("E_MAIL") or row.values.get("EMAIL")),
                        phone=self._text(row.values.get("TELEFONE") or row.values.get("CELULAR")),
                        source_row_identifier=str(row.row_number),
                    )
                    counts["employees_processed"] += 1
                    most_urgent = None
                    for header, requirement_type in types_by_header.items():
                        raw = row.values.get(header)
                        try:
                            expiry = parse_sheet_date(raw)
                        except ValueError:
                            counts["errors"] += 1
                            continue
                        if expiry is None:
                            requirement_repo.synchronize(
                                company_id=company.id,
                                employee_id=employee.id,
                                requirement_type_id=requirement_type.id,
                                expiry_date=None,
                                source_value=None,
                                source_column=requirement_type.spreadsheet_header,
                                calculated_status=CalculatedStatus.SEM_DATA,
                                last_synced_at=datetime.now().astimezone(),
                            )
                            continue
                        assessment = ExpirationPolicy.assess(expiry, self.today)
                        record = requirement_repo.synchronize(
                            company_id=company.id,
                            employee_id=employee.id,
                            requirement_type_id=requirement_type.id,
                            expiry_date=expiry,
                            source_value=self._text(raw),
                            source_column=requirement_type.spreadsheet_header,
                            calculated_status=assessment.status,
                            last_synced_at=datetime.now().astimezone(),
                        )
                        counts["requirements_processed"] += 1
                        if assessment.status == CalculatedStatus.REGULAR:
                            counts["valid"] += 1
                        elif assessment.status == CalculatedStatus.VENCE_HOJE:
                            counts["due_today"] += 1
                        elif assessment.status == CalculatedStatus.VENCIDO:
                            counts["expired"] += 1
                        else:
                            counts["warnings"] += 1
                        if assessment.days_remaining is not None and (
                            most_urgent is None or assessment.days_remaining < most_urgent[0]
                        ):
                            most_urgent = (
                                assessment.days_remaining,
                                requirement_type,
                                record,
                                assessment,
                            )
                        email_sent = notification.repository.sent_rule_days(record.id, channel="EMAIL")
                        email_selected = ExpirationPolicy.choose_notification_rule(
                            assessment.days_remaining, email_sent
                        )
                        email_expired_pending = (
                            assessment.days_remaining is not None
                            and assessment.days_remaining < 0
                            and None not in email_sent
                        )
                        should_send_email = (
                            assessment.days_remaining is not None
                            and (email_expired_pending or email_selected is not None)
                            and email_selected in rules
                        )
                        if should_send_email and self._has_email_recipient(company, employee):
                            notification.queue(
                                company,
                                employee,
                                record,
                                requirement_type,
                                rules[email_selected],
                                assessment.days_remaining,
                            )
                        telegram_sent = telegram_notifications.sent_rule_days(
                            record.id, channel="TELEGRAM"
                        )
                        telegram_selected = ExpirationPolicy.choose_notification_rule(
                            assessment.days_remaining, telegram_sent
                        )
                        telegram_expired_pending = (
                            assessment.days_remaining is not None
                            and assessment.days_remaining < 0
                            and None not in telegram_sent
                        )
                        should_send_telegram = (
                            assessment.days_remaining is not None
                            and (telegram_expired_pending or telegram_selected is not None)
                            and telegram_selected in rules
                        )
                        if should_send_telegram:
                            telegram_item = self._queue_telegram_item(
                                company,
                                employee,
                                record,
                                requirement_type,
                                rules[telegram_selected],
                                assessment.days_remaining,
                            )
                            if telegram_item:
                                telegram_items.append(telegram_item)
                    update_values.extend(
                        self._row_update(
                            company, mapper, row.row_number, row.automation_id, most_urgent
                        )
                    )
                except Exception:
                    counts["errors"] += 1
                    continue
            counts.update(notification.flush())
            self.session.commit()
            self.sheets.ensure_sheet(company, company.history_sheet_name, HISTORY_HEADERS)
            self.sheets.ensure_sheet(company, company.executions_sheet_name, EXECUTION_HEADERS)
            self.sheets.batch_update(company, update_values)
            self.sheets.append_rows(
                company,
                company.history_sheet_name,
                self._history_rows(company, execution),
            )
            execution.status = (
                ExecutionStatus.PARTIAL_SUCCESS if counts["errors"] else ExecutionStatus.SUCCESS
            )
        except Exception:
            self.session.rollback()
            execution = self.session.get(SyncExecution, execution.id)
            execution.status = ExecutionStatus.FAILED
            counts["errors"] += 1
        execution.finished_at = datetime.now().astimezone()
        self._apply_counts(execution, counts)
        execution.summary = dict(counts)
        self.session.commit()
        try:
            self.sheets.append_rows(
                company,
                company.executions_sheet_name,
                [
                    [
                        str(execution.id),
                        company.code,
                        execution.started_at.isoformat(),
                        execution.finished_at.isoformat(),
                        execution.status,
                        execution.rows_read,
                        execution.employees_processed,
                        execution.requirements_processed,
                        execution.valid_count,
                        execution.warning_count,
                        execution.due_today_count,
                        execution.expired_count,
                        execution.emails_sent,
                        execution.duplicates_skipped,
                        execution.errors_count,
                    ]
                ],
            )
        except Exception:
            pass
        return {
            "company_code": company.code,
            "status": execution.status,
            **dict(counts),
            "_telegram_items": telegram_items,
        }

    def _run_local_company(self, company: Company, trigger_type: str) -> dict:
        execution = SyncExecution(
            company_id=company.id, status=ExecutionStatus.RUNNING, trigger_type=trigger_type
        )
        self.session.add(execution)
        self.session.commit()
        counts: Counter[str] = Counter()
        failure_detail: str | None = None
        telegram_items: list[dict[str, object]] = []
        try:
            rows = self.session.execute(
                select(RequirementRecord, Employee, RequirementType)
                .join(Employee)
                .join(RequirementType)
                .where(
                    RequirementRecord.company_id == company.id,
                    RequirementRecord.active.is_(True),
                )
            ).all()
            counts["requirements_processed"] = len(rows)
            counts["rows_read"] = len({employee.id for _, employee, _ in rows})
            counts["employees_processed"] = counts["rows_read"]
            rules = {
                rule.days_before_expiry: rule
                for rule in self.session.scalars(
                    select(NotificationRule).where(
                        NotificationRule.enabled.is_(True), NotificationRule.send_email.is_(True)
                    )
                )
            }
            notification = BatchNotificationService(self.session, self.email)
            telegram_notifications = SQLAlchemyNotificationRepository(self.session)
            telegram_items = []
            for record, employee, requirement_type in rows:
                assessment = ExpirationPolicy.assess(record.expiry_date, self.today)
                record.calculated_status = assessment.status
                record.last_synced_at = datetime.now().astimezone()
                if assessment.status == CalculatedStatus.REGULAR:
                    counts["valid"] += 1
                elif assessment.status == CalculatedStatus.VENCE_HOJE:
                    counts["due_today"] += 1
                elif assessment.status == CalculatedStatus.VENCIDO:
                    counts["expired"] += 1
                else:
                    counts["warnings"] += 1
                if assessment.days_remaining is None:
                    continue
                email_sent = notification.repository.sent_rule_days(record.id, channel="EMAIL")
                email_selected = ExpirationPolicy.choose_notification_rule(
                    assessment.days_remaining, email_sent
                )
                email_expired_pending = assessment.days_remaining < 0 and None not in email_sent
                should_send_email = (
                    (email_expired_pending or email_selected is not None) and email_selected in rules
                )
                if should_send_email and self._has_email_recipient(company, employee):
                    notification.queue(
                        company,
                        employee,
                        record,
                        requirement_type,
                        rules[email_selected],
                        assessment.days_remaining,
                    )
                telegram_sent = telegram_notifications.sent_rule_days(record.id, channel="TELEGRAM")
                telegram_selected = ExpirationPolicy.choose_notification_rule(
                    assessment.days_remaining, telegram_sent
                )
                telegram_expired_pending = assessment.days_remaining < 0 and None not in telegram_sent
                should_send_telegram = (
                    (telegram_expired_pending or telegram_selected is not None)
                    and telegram_selected in rules
                )
                if should_send_telegram:
                    telegram_item = self._queue_telegram_item(
                        company,
                        employee,
                        record,
                        requirement_type,
                        rules[telegram_selected],
                        assessment.days_remaining,
                    )
                    if telegram_item:
                        telegram_items.append(telegram_item)
            counts.update(notification.flush())
            execution.status = (
                ExecutionStatus.PARTIAL_SUCCESS if counts["errors"] else ExecutionStatus.SUCCESS
            )
            if notification.last_error:
                failure_detail = notification.last_error
        except Exception:
            logger.exception(
                "Falha ao preparar avisos da empresa %s durante a execução %s",
                company.code,
                execution.id,
            )
            self.session.rollback()
            execution = self.session.get(SyncExecution, execution.id)
            execution.status = ExecutionStatus.FAILED
            counts["errors"] += 1
            failure_detail = (
                "Não foi possível preparar os avisos. Consulte o log da automação para detalhes."
            )
        execution.finished_at = datetime.now().astimezone()
        self._apply_counts(execution, counts)
        execution.summary = dict(counts)
        self.session.commit()
        result = {
            "company_code": company.code,
            "status": execution.status,
            **dict(counts),
            "_telegram_items": telegram_items,
        }
        if failure_detail:
            result["detail"] = failure_detail
        return result

    @staticmethod
    def _text(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _apply_counts(execution: SyncExecution, counts: Counter[str]) -> None:
        for field, key in (
            ("rows_read", "rows_read"),
            ("employees_processed", "employees_processed"),
            ("requirements_processed", "requirements_processed"),
            ("valid_count", "valid"),
            ("warning_count", "warnings"),
            ("due_today_count", "due_today"),
            ("expired_count", "expired"),
            ("emails_sent", "emails_sent"),
            ("duplicates_skipped", "duplicates_skipped"),
            ("errors_count", "errors"),
        ):
            setattr(execution, field, counts[key])

    def _has_email_recipient(self, company: Company, employee: Employee) -> bool:
        return bool(company.responsible_emails) or (
            self.email.settings.notify_employee and bool(employee.email)
        )

    def _queue_telegram_item(
        self,
        company: Company,
        employee: Employee,
        record: RequirementRecord,
        requirement_type: RequirementType,
        rule: NotificationRule,
        days_remaining: int,
    ) -> dict[str, object] | None:
        if not self.telegram or not self.telegram.configured_for(company.telegram_chat_id):
            return None
        target_chat_id = company.telegram_chat_id or self.telegram.settings.telegram_chat_id
        event, created = SQLAlchemyNotificationRepository(self.session).create_pending(
            NotificationEvent(
                company_id=company.id,
                employee_id=employee.id,
                requirement_record_id=record.id,
                notification_rule_id=rule.id,
                expiry_date=record.expiry_date,
                notification_key=notification_key(
                    company.id,
                    employee.id,
                    requirement_type.id,
                    record.expiry_date,
                    rule.code,
                    f"TELEGRAM:{target_chat_id}",
                ),
                channel="TELEGRAM",
                destination_masked="Grupo Telegram",
                status=EventStatus.PENDING,
            )
        )
        if not created and event.status == EventStatus.SENT:
            return None
        return {
            "employee_name": employee.full_name,
            "requirement_type": requirement_type.name,
            "expiry_date": record.expiry_date,
            "days_remaining": days_remaining,
            "event": event,
        }

    def _send_telegram_summary(self, company: Company, result: dict, trigger_type: str) -> str:
        items = result.pop("_telegram_items", [])
        if not self.telegram or not self.telegram.configured_for(company.telegram_chat_id):
            return "NÃO CONFIGURADO"
        has_activity = any(
            int(result.get(key, 0)) for key in ("emails_sent", "due_today", "expired", "errors")
        ) or bool(items)
        if trigger_type != "MANUAL" and not has_activity:
            return "SEM ATIVIDADE"
        try:
            self.telegram.send_summary(
                self._telegram_message(company, result, items),
                chat_id=company.telegram_chat_id,
            )
            self._finish_telegram_items(items, EventStatus.SENT)
            return "ENVIADO"
        except Exception as error:
            logger.exception("Falha ao enviar resumo do Telegram para a empresa %s", company.code)
            self._finish_telegram_items(items, EventStatus.FAILED, str(error))
            return "FALHOU"

    def _finish_telegram_items(
        self,
        items: list[dict[str, object]],
        status: EventStatus,
        error_message: str | None = None,
    ) -> None:
        for item in items:
            event = item.get("event")
            if not isinstance(event, NotificationEvent):
                continue
            event.status = status
            event.attempts += 1
            event.sent_at = datetime.now().astimezone() if status == EventStatus.SENT else None
            event.error_message = error_message[:500] if error_message else None
        if items:
            self.session.commit()
    @staticmethod
    def _telegram_message(company: Company, result: dict, items: list[dict[str, object]]) -> str:
        lines = [
            "📋 Resumo da automação de vencimentos",
            f"Empresa: {company.name}",
            f"Status: {result['status']}",
        ]
        if items:
            lines.extend(["", f"🔔 Avisos deste lote: {len(items)}", ""])
            by_expiry: dict[date, list[dict[str, object]]] = defaultdict(list)
            for item in items:
                expiry_date = item["expiry_date"]
                if isinstance(expiry_date, date):
                    by_expiry[expiry_date].append(item)
            for expiry_date in sorted(by_expiry):
                day_items = sorted(by_expiry[expiry_date], key=lambda item: str(item["employee_name"]))
                days = int(day_items[0]["days_remaining"])
                quantity = len(day_items)
                if days < 0:
                    day_label = "dia" if abs(days) == 1 else "dias"
                    lines.append(
                        f"🔴 Vencidos em {expiry_date.strftime('%d/%m/%Y')} "
                        f"(há {abs(days)} {day_label}) — {quantity} item(ns)"
                    )
                elif days == 0:
                    lines.append(f"🟠 Vencem hoje ({expiry_date.strftime('%d/%m/%Y')}) — {quantity} item(ns)")
                else:
                    day_label = "dia" if days == 1 else "dias"
                    lines.append(
                        f"📅 Vencem em {expiry_date.strftime('%d/%m/%Y')} "
                        f"(faltam {days} {day_label}) — {quantity} item(ns)"
                    )
                for item in day_items:
                    lines.append(
                        f"• {item['employee_name']} — {item['requirement_type']} "
                        f"({ExecutionService._telegram_days_label(int(item['days_remaining']))})"
                    )
                lines.append("")
        else:
            lines.extend(["", "Nenhum novo aviso de vencimento foi gerado nesta execução.", ""])
        lines.extend(
            [
                f"Colaboradores analisados: {result.get('employees_processed', 0)}",
                f"Vencem hoje: {result.get('due_today', 0)}",
                f"Itens vencidos: {result.get('expired', 0)}",
                f"E-mails enviados: {result.get('emails_sent', 0)}",
                f"Falhas: {result.get('errors', 0)}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _telegram_days_label(days: int) -> str:
        if days < 0:
            return f"vencido há {abs(days)} {'dia' if abs(days) == 1 else 'dias'}"
        if days == 0:
            return "vence hoje"
        return f"faltam {days} {'dia' if days == 1 else 'dias'}"

    @staticmethod
    def _row_update(
        company: Company, mapper: SheetMapper, row_number: int, automation_id: str, urgent
    ):
        # Somente colunas de automação existentes são atualizadas em lote.
        if urgent is None:
            return []
        days, requirement_type, _, assessment = urgent
        values = {
            "ID_AUTOMACAO": automation_id,
            "ITEM_MAIS_PROXIMO": requirement_type.name,
            "PROXIMO_VENCIMENTO": assessment.expiry_date.strftime("%d/%m/%Y"),
            "DIAS_RESTANTES": days,
            "STATUS_GERAL": assessment.status,
            "ULTIMA_VERIFICACAO": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        updates = []
        for header, value in values.items():
            index = mapper.headers.get(header)
            if index is not None:
                column = ExecutionService._column_letter(index + 1)
                updates.append(
                    {
                        "range": f"'{company.main_sheet_name}'!{column}{row_number}",
                        "values": [[value]],
                    }
                )
        return updates

    @staticmethod
    def _column_letter(number: int) -> str:
        result = ""
        while number:
            number, rem = divmod(number - 1, 26)
            result = chr(65 + rem) + result
        return result

    def _history_rows(self, company: Company, execution: SyncExecution) -> list[list[object]]:
        rows = self.session.execute(
            select(
                NotificationEvent,
                Employee,
                RequirementRecord,
                RequirementType,
                NotificationRule,
            )
            .join(Employee, Employee.id == NotificationEvent.employee_id)
            .join(
                RequirementRecord, RequirementRecord.id == NotificationEvent.requirement_record_id
            )
            .join(RequirementType, RequirementType.id == RequirementRecord.requirement_type_id)
            .join(NotificationRule, NotificationRule.id == NotificationEvent.notification_rule_id)
            .where(
                NotificationEvent.company_id == company.id,
                NotificationEvent.created_at >= execution.started_at,
            )
        ).all()
        return [
            [
                str(event.id),
                str(execution.id),
                company.code,
                employee.automation_id,
                employee.full_name,
                requirement_type.name,
                event.expiry_date.strftime("%d/%m/%Y"),
                (event.expiry_date - self.today).days,
                rule.code,
                rule.severity,
                event.channel,
                event.destination_masked,
                event.sent_at.isoformat() if event.sent_at else None,
                event.status,
                event.provider_message_id,
                event.error_message,
                event.notification_key,
            ]
            for event, employee, _, requirement_type, rule in rows
        ]

    @staticmethod
    def _summary(root: SyncExecution, companies: list[dict]) -> dict:
        keys = (
            "rows_read",
            "employees_processed",
            "requirements_processed",
            "valid",
            "warnings",
            "due_today",
            "expired",
            "emails_sent",
            "duplicates_skipped",
            "errors",
        )
        totals = {key: sum(int(company.get(key, 0)) for company in companies) for key in keys}
        return {
            "execution_id": str(root.id),
            "status": root.status,
            "started_at": root.started_at.isoformat(),
            "finished_at": root.finished_at.isoformat() if root.finished_at else None,
            "companies_processed": len(companies),
            "companies_succeeded": sum(item["status"] != "FAILED" for item in companies),
            "companies_failed": sum(item["status"] == "FAILED" for item in companies),
            "totals": totals,
            "companies": companies,
        }
