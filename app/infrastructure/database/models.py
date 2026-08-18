from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, UUIDTimestampMixin


class Company(UUIDTimestampMixin, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(String(255), nullable=False)
    main_sheet_name: Mapped[str] = mapped_column(String(255), default="Controle", nullable=False)
    history_sheet_name: Mapped[str] = mapped_column(
        String(255), default="Historico_Notificacoes", nullable=False
    )
    executions_sheet_name: Mapped[str] = mapped_column(
        String(255), default="Execucoes", nullable=False
    )
    responsible_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Employee(UUIDTimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("company_id", "automation_id"),)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    automation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_identifier: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mobilizing_company: Mapped[str | None] = mapped_column(String(255))
    badge_id: Mapped[str | None] = mapped_column(String(128))
    cpf_protected: Mapped[str | None] = mapped_column(String(255))
    rg_protected: Mapped[str | None] = mapped_column(String(255))
    admission_date: Mapped[date | None] = mapped_column(Date)
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(320))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Vehicle(UUIDTimestampMixin, Base):
    __tablename__ = "vehicles"
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"))
    plate: Mapped[str | None] = mapped_column(String(16))
    brand: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(128))
    year: Mapped[int | None] = mapped_column(Integer)
    chassis: Mapped[str | None] = mapped_column(String(128))
    renavam: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(64))
    engine_specification: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RequirementType(UUIDTimestampMixin, Base):
    __tablename__ = "requirement_types"
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    spreadsheet_header: Mapped[str | None] = mapped_column(String(255))
    status_header: Mapped[str | None] = mapped_column(String(255))
    expected_format: Mapped[str | None] = mapped_column(String(64))
    requires_expiry_date: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RequirementRecord(UUIDTimestampMixin, Base):
    __tablename__ = "requirement_records"
    __table_args__ = (
        Index("ix_requirement_records_company_expiry", "company_id", "expiry_date"),
        Index("ix_requirement_records_employee", "employee_id"),
        Index("ix_requirement_records_status", "calculated_status"),
        Index("ix_requirement_records_type", "requirement_type_id"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))
    requirement_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_types.id"), nullable=False
    )
    completion_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_value: Mapped[str | None] = mapped_column(String(255))
    source_status: Mapped[str | None] = mapped_column(String(255))
    calculated_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_column: Mapped[str | None] = mapped_column(String(255))
    cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationRule(UUIDTimestampMixin, Base):
    __tablename__ = "notification_rules"
    days_before_expiry: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    send_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationEvent(UUIDTimestampMixin, Base):
    __tablename__ = "notification_events"
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"), nullable=False)
    requirement_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requirement_records.id"), nullable=False
    )
    notification_rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_rules.id"), nullable=False
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    notification_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination_masked: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncExecution(UUIDTimestampMixin, Base):
    __tablename__ = "sync_executions"
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(64), default="MANUAL", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employees_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requirements_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_today_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expired_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    emails_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
