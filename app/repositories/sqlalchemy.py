from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums.core import EventStatus
from app.infrastructure.database.models import (
    Company,
    Employee,
    NotificationEvent,
    NotificationRule,
    RequirementRecord,
    SyncExecution,
)


class SQLAlchemyCompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def active(self) -> list[Company]:
        return list(
            self.session.scalars(
                select(Company).where(Company.active.is_(True)).order_by(Company.code)
            )
        )

    def get(self, company_id: uuid.UUID) -> Company | None:
        return self.session.get(Company, company_id)


class SQLAlchemyEmployeeRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, company_id: uuid.UUID, automation_id: str, **values: object) -> Employee:
        statement = select(Employee).where(
            Employee.company_id == company_id, Employee.automation_id == automation_id
        )
        employee = self.session.scalar(statement)
        if employee is None:
            employee = Employee(company_id=company_id, automation_id=automation_id, **values)
            self.session.add(employee)
        else:
            for key, value in values.items():
                setattr(employee, key, value)
            employee.active = True
        employee.last_synced_at = datetime.now().astimezone()
        self.session.flush()
        return employee


class SQLAlchemyRequirementRepository:
    def __init__(self, session: Session):
        self.session = session

    def synchronize(
        self,
        *,
        company_id: uuid.UUID,
        employee_id: uuid.UUID,
        requirement_type_id: uuid.UUID,
        expiry_date: date | None,
        **values: object,
    ) -> RequirementRecord:
        current = self.session.scalar(
            select(RequirementRecord).where(
                RequirementRecord.company_id == company_id,
                RequirementRecord.employee_id == employee_id,
                RequirementRecord.requirement_type_id == requirement_type_id,
                RequirementRecord.active.is_(True),
            )
        )
        if expiry_date is None:
            if current:
                current.active = False
                current.renewed_at = datetime.now().astimezone()
                current.last_synced_at = datetime.now().astimezone()
                self.session.flush()
                return current
            # Não cria ciclos vazios: a ausência de data apenas desativa o ciclo vigente.
            return RequirementRecord(
                company_id=company_id,
                employee_id=employee_id,
                requirement_type_id=requirement_type_id,
                expiry_date=None,
                cycle_number=0,
                active=False,
                calculated_status="SEM_DATA",
                **values,
            )
        if current and current.expiry_date == expiry_date:
            for key, value in values.items():
                setattr(current, key, value)
            current.last_synced_at = datetime.now().astimezone()
            self.session.flush()
            return current
        cycle = 1
        if current:
            current.active = False
            current.renewed_at = datetime.now().astimezone()
            cycle = current.cycle_number + 1
        record = RequirementRecord(
            company_id=company_id,
            employee_id=employee_id,
            requirement_type_id=requirement_type_id,
            expiry_date=expiry_date,
            cycle_number=cycle,
            active=expiry_date is not None,
            **values,
        )
        self.session.add(record)
        self.session.flush()
        return record


class SQLAlchemyNotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def sent_rule_days(
        self, requirement_record_id: uuid.UUID, channel: str | None = None
    ) -> set[int | None]:
        statement = select(NotificationRule.days_before_expiry).join(NotificationEvent).where(
            NotificationEvent.requirement_record_id == requirement_record_id,
            NotificationEvent.status == EventStatus.SENT,
        )
        if channel:
            statement = statement.where(NotificationEvent.channel == channel)
        rows = self.session.execute(statement)
        return set(rows.scalars())

    def create_pending(self, event: NotificationEvent) -> tuple[NotificationEvent, bool]:
        try:
            with self.session.begin_nested():
                self.session.add(event)
                self.session.flush()
            return event, True
        except IntegrityError:
            existing = self.session.scalar(
                select(NotificationEvent).where(
                    NotificationEvent.notification_key == event.notification_key
                )
            )
            if existing is None:
                raise
            return existing, False


class SQLAlchemyExecutionRepository:
    def __init__(self, session: Session):
        self.session = session

    def running_for(self, company_id: uuid.UUID | None) -> bool:
        return (
            self.session.scalar(
                select(SyncExecution.id).where(
                    SyncExecution.company_id == company_id, SyncExecution.status == "RUNNING"
                )
            )
            is not None
        )

    def latest(self) -> SyncExecution | None:
        return self.session.scalar(select(SyncExecution).order_by(SyncExecution.started_at.desc()))

    def get(self, execution_id: uuid.UUID) -> SyncExecution | None:
        return self.session.get(SyncExecution, execution_id)
