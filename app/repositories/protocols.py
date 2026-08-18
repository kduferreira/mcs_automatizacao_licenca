from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol

from app.infrastructure.database.models import (
    Company,
    Employee,
    NotificationEvent,
    RequirementRecord,
)


class SpreadsheetGateway(Protocol):
    def read_main_sheet(self, company: Company) -> list[list[object]]: ...
    def batch_update(self, company: Company, values: list[dict[str, object]]) -> None: ...
    def append_rows(self, company: Company, sheet_name: str, rows: list[list[object]]) -> None: ...
    def ensure_sheet(self, company: Company, sheet_name: str, headers: list[str]) -> None: ...


class EmailGateway(Protocol):
    def send(self, *, recipients: list[str], subject: str, text: str, html: str) -> str | None: ...


class CompanyRepository(Protocol):
    def active(self) -> list[Company]: ...
    def get(self, company_id: uuid.UUID) -> Company | None: ...


class EmployeeRepository(Protocol):
    def upsert(self, company_id: uuid.UUID, automation_id: str, **values: object) -> Employee: ...


class RequirementRepository(Protocol):
    def synchronize(
        self,
        *,
        company_id: uuid.UUID,
        employee_id: uuid.UUID,
        requirement_type_id: uuid.UUID,
        expiry_date: date | None,
        **values: object,
    ) -> RequirementRecord: ...


class NotificationRepository(Protocol):
    def create_pending(self, event: NotificationEvent) -> tuple[NotificationEvent, bool]: ...
