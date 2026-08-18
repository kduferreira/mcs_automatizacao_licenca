from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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
