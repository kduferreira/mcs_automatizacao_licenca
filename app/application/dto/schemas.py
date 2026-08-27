from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
    active: bool


class ExpirationResponse(BaseModel):
    requirement_record_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    item: str
    expiry_date: date | None
    days_remaining: int | None
    status: str


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    requirement_record_id: uuid.UUID
    status: str
    sent_at: datetime | None
    attempts: int
    destination_masked: str | None
    error_message: str | None


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_read: int
    employees_processed: int
    requirements_processed: int
    emails_sent: int
    duplicates_skipped: int
    errors_count: int
    summary: dict | None


class DashboardCompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    active: bool
    expirations: int
    due_today: int
    expired: int
    notifications_pending: int


class MessageTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    channel: str
    subject: str | None
    body: str
    active: bool


class MessageTemplateUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1, max_length=10000)
    active: bool = True


class SpreadsheetSheet(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    rows: list[list[object]] = Field(min_length=1, max_length=5000)


class SpreadsheetImportRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    company_code: str = Field(min_length=2, max_length=64)
    source_name: str = Field(min_length=1, max_length=255)
    responsible_emails: list[str] = Field(default_factory=list, max_length=20)
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    rows: list[list[object]] | None = Field(default=None, max_length=5000)
    sheets: list[SpreadsheetSheet] = Field(default_factory=list, max_length=30)

    @field_validator("company_code")
    @classmethod
    def normalize_company_code(cls, value: str) -> str:
        normalized = "".join(
            character if character.isalnum() else "_" for character in value.upper().strip()
        ).strip("_")
        if not normalized:
            raise ValueError("código da empresa inválido")
        return normalized[:64]

    @field_validator("responsible_emails")
    @classmethod
    def normalize_emails(cls, values: list[str]) -> list[str]:
        return [value.strip().lower() for value in values if value.strip()]

    @field_validator("telegram_chat_id")
    @classmethod
    def normalize_telegram_chat_id(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def has_data(self):
        if not self.sheets and not self.rows:
            raise ValueError("envie ao menos uma aba com dados")
        return self

    def legacy_sheet(self) -> SpreadsheetSheet:
        return SpreadsheetSheet(name=self.source_name, rows=self.rows or [])


class SpreadsheetImportResponse(BaseModel):
    company: CompanyResponse
    employees_imported: int
    requirements_imported: int
    employees_deactivated: int
    requirements_deactivated: int
    date_columns: list[str]
    invalid_rows: int
    invalid_dates: int
    sheets_imported: int
