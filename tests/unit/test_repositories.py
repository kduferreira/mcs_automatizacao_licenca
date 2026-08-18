from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.enums.core import CalculatedStatus, EventStatus
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import (
    Company,
    NotificationEvent,
    NotificationRule,
    RequirementRecord,
    RequirementType,
)
from app.repositories.sqlalchemy import (
    SQLAlchemyEmployeeRepository,
    SQLAlchemyNotificationRepository,
    SQLAlchemyRequirementRepository,
)


def build_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_employee_isolation_and_requirement_renewal():
    session = build_session()
    first, second = (
        Company(name="A", code="A", spreadsheet_id="a", responsible_emails=[]),
        Company(name="B", code="B", spreadsheet_id="b", responsible_emails=[]),
    )
    item = RequirementType(code="ASO", name="ASO", category="ASO", spreadsheet_header="ASO")
    session.add_all([first, second, item])
    session.commit()
    employees = SQLAlchemyEmployeeRepository(session)
    a, b = (
        employees.upsert(first.id, "X", full_name="Pessoa A"),
        employees.upsert(second.id, "X", full_name="Pessoa B"),
    )
    assert a.id != b.id
    requirements = SQLAlchemyRequirementRepository(session)
    old = requirements.synchronize(
        company_id=first.id,
        employee_id=a.id,
        requirement_type_id=item.id,
        expiry_date=date(2026, 8, 20),
        calculated_status=CalculatedStatus.ALERTA_VERMELHO,
    )
    new = requirements.synchronize(
        company_id=first.id,
        employee_id=a.id,
        requirement_type_id=item.id,
        expiry_date=date(2027, 8, 20),
        calculated_status=CalculatedStatus.REGULAR,
    )
    assert not old.active and old.renewed_at and new.active and new.cycle_number == 2


def test_notification_key_is_idempotent():
    session = build_session()
    company = Company(name="A", code="A", spreadsheet_id="a", responsible_emails=[])
    item = RequirementType(code="ASO", name="ASO", category="ASO")
    session.add_all([company, item])
    session.commit()
    employee = SQLAlchemyEmployeeRepository(session).upsert(company.id, "E", full_name="Pessoa")
    record = RequirementRecord(
        company_id=company.id,
        employee_id=employee.id,
        requirement_type_id=item.id,
        expiry_date=date.today(),
        calculated_status="VENCE_HOJE",
    )
    rule = NotificationRule(days_before_expiry=0, code="H", severity="C", template_code="H")
    session.add_all([record, rule])
    session.commit()
    repo = SQLAlchemyNotificationRepository(session)
    kwargs = dict(
        company_id=company.id,
        employee_id=employee.id,
        requirement_record_id=record.id,
        notification_rule_id=rule.id,
        expiry_date=date.today(),
        notification_key="same",
        channel="EMAIL",
        status=EventStatus.PENDING,
    )
    _, created = repo.create_pending(NotificationEvent(**kwargs))
    session.commit()
    _, duplicate = repo.create_pending(NotificationEvent(**kwargs))
    assert created and not duplicate
