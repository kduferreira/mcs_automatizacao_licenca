from __future__ import annotations

import calendar
import hashlib
import re
from collections import Counter
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.security import require_api_key
from app.application.dto.schemas import SpreadsheetImportRequest, SpreadsheetImportResponse
from app.application.services.sheet_mapper import SheetMapper
from app.domain.enums.core import RequirementCategory
from app.domain.rules.expiration import ExpirationPolicy
from app.domain.rules.normalization import normalize_header, parse_sheet_date
from app.infrastructure.database.models import Company, RequirementType
from app.infrastructure.database.session import get_session
from app.repositories.sqlalchemy import (
    SQLAlchemyEmployeeRepository,
    SQLAlchemyRequirementRepository,
)

router = APIRouter(
    prefix="/api/v1/imports", tags=["imports"], dependencies=[Depends(require_api_key)]
)

LOCAL_UPLOAD_PREFIX = "LOCAL_UPLOAD:"
IDENTITY_HEADERS = {
    "ID_AUTOMACAO", "NOME_COMPLETO", "UNIDADE", "E_MAIL", "EMAIL", "CPF", "RG",
    "TELEFONE", "CELULAR", "CARGO", "FUNCAO", "DATA_ADMISSAO", "DATA_NASCIMENTO",
    "NASCIMENTO",
}
GENERIC_HEADERS = {"PRAZO", "VIGENCIA", "DATA", "STATUS", "SITUACAO"}
MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def _category(header: str) -> str:
    if "ASO" in header:
        return RequirementCategory.ASO
    if "NR_" in header or "TREINAMENTO" in header:
        return RequirementCategory.TRAINING
    if "VACINA" in header:
        return RequirementCategory.VACCINE
    if "AMBIENT" in header or "RAC" in header:
        return RequirementCategory.AMBIENTATION
    if "CNH" in header or "ART" in header:
        return RequirementCategory.DOCUMENT
    return RequirementCategory.OTHER


def _new_requirement_code(header: str) -> str:
    clean = re.sub(r"[^A-Z0-9_]", "", normalize_header(header))[:72]
    digest = hashlib.sha1(header.encode()).hexdigest()[:8].upper()
    return f"IMPORT_{clean or 'ITEM'}_{digest}"


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _parse_date(value: object) -> date | None:
    try:
        return parse_sheet_date(value)
    except ValueError:
        raw = _text(value)
        if not raw:
            return None
        matches = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", raw)
        for candidate in reversed(matches):
            parts = re.split(r"[/-]", candidate)
            if len(parts[-1]) == 2:
                candidate = f"{parts[0]}/{parts[1]}/20{parts[2]}"
            try:
                return parse_sheet_date(candidate)
            except ValueError:
                continue
        month = re.search(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?[-/]?(\d{2,4})\b", raw.lower())
        if month:
            year = int(month.group(2))
            year += 2000 if year < 100 else 0
            number = MONTHS[month.group(1)]
            return date(year, number, calendar.monthrange(year, number)[1])
        return None


def _first_employee_header(rows: list[list[object]]) -> int | None:
    for index, row in enumerate(rows[:25]):
        if "NOME_COMPLETO" in {normalize_header(str(cell)) for cell in row}:
            return index
    return None


def _ensure_type(
    name: str, types_by_header: dict[str, RequirementType], session: Session
) -> RequirementType:
    key = normalize_header(name)
    if key in types_by_header:
        return types_by_header[key]
    code = _new_requirement_code(name)
    item = session.scalar(select(RequirementType).where(RequirementType.code == code))
    if item is None:
        item = RequirementType(
            code=code, name=name[:255], category=_category(key), spreadsheet_header=name[:255]
        )
        session.add(item)
        session.flush()
    types_by_header[key] = item
    return item


def _column_label(rows: list[list[object]], row_index: int, column_index: int) -> str | None:
    for index in range(row_index - 1, -1, -1):
        value = _text(rows[index][column_index] if column_index < len(rows[index]) else None)
        if value and normalize_header(value) not in GENERIC_HEADERS:
            return value
    return None


def _row_label(row: list[object], column_index: int) -> str | None:
    for index in range(min(column_index - 1, len(row) - 1), -1, -1):
        value = _text(row[index])
        if value and normalize_header(value) not in GENERIC_HEADERS:
            return value
    return None


@router.post("/spreadsheet", response_model=SpreadsheetImportResponse, status_code=status.HTTP_201_CREATED)
def import_spreadsheet(payload: SpreadsheetImportRequest, session: Session = Depends(get_session)):
    company = session.scalar(select(Company).where(Company.code == payload.company_code))
    if company is None:
        company = Company(name=payload.company_name, code=payload.company_code, spreadsheet_id=f"{LOCAL_UPLOAD_PREFIX}{payload.company_code}", responsible_emails=payload.responsible_emails)
        session.add(company)
        session.flush()
    else:
        company.name, company.responsible_emails, company.active = payload.company_name, payload.responsible_emails, True

    types_by_header = {
        normalize_header(item.spreadsheet_header or ""): item
        for item in session.scalars(select(RequirementType).where(RequirementType.active.is_(True)))
        if item.spreadsheet_header
    }
    employees = SQLAlchemyEmployeeRepository(session)
    requirements = SQLAlchemyRequirementRepository(session)
    counts: Counter[str] = Counter()
    imported_types: set[str] = set()
    today = datetime.now().date()
    sheets = payload.sheets or [payload.legacy_sheet()]
    for sheet in sheets:
        header_row = _first_employee_header(sheet.rows)
        if header_row is None:
            _import_company_matrix(sheet.name, sheet.rows, company, employees, requirements, types_by_header, imported_types, counts, today)
        else:
            _import_employee_table(sheet.name, sheet.rows[header_row:], company, employees, requirements, types_by_header, imported_types, counts, today)
    if not counts["requirements"]:
        session.rollback()
        raise HTTPException(422, "Nenhuma data de vencimento foi encontrada nas abas selecionadas.")
    session.commit()
    return SpreadsheetImportResponse(company=company, employees_imported=counts["employees"], requirements_imported=counts["requirements"], date_columns=sorted(imported_types), invalid_rows=counts["invalid_rows"], invalid_dates=counts["invalid_dates"], sheets_imported=len(sheets))


def _import_employee_table(sheet_name, rows, company, employees, requirements, types, names, counts, today):
    mapper = SheetMapper(rows)
    date_columns = {}
    for header, index in mapper.headers.items():
        if header in IDENTITY_HEADERS:
            continue
        if any(_parse_date(row[index] if index < len(row) else None) for row in mapper.rows):
            title = f"{sheet_name}: {mapper.original_headers[index]}"
            date_columns[header] = _ensure_type(title, types, employees.session)
            names.add(title)
    for mapped in mapper.mapped_rows():
        name = _text(mapped.values.get("NOME_COMPLETO"))
        if not name:
            counts["invalid_rows"] += 1
            continue
        automation_id = mapped.automation_id if "ID_AUTOMACAO" in mapper.headers else f"IMPORT-{company.code}-{sheet_name}-{mapped.row_number}"[:64]
        employee = employees.upsert(company.id, automation_id, full_name=name, unit=_text(mapped.values.get("UNIDADE")), email=_text(mapped.values.get("E_MAIL") or mapped.values.get("EMAIL")), phone=_text(mapped.values.get("TELEFONE") or mapped.values.get("CELULAR")), source_row_identifier=f"{sheet_name}:{mapped.row_number}")
        counts["employees"] += 1
        for header, requirement_type in date_columns.items():
            raw = mapped.values.get(header)
            expiry = _parse_date(raw)
            if not expiry:
                continue
            assessment = ExpirationPolicy.assess(expiry, today)
            requirements.synchronize(company_id=company.id, employee_id=employee.id, requirement_type_id=requirement_type.id, expiry_date=expiry, source_value=_text(raw), source_column=requirement_type.spreadsheet_header, calculated_status=assessment.status, last_synced_at=datetime.now().astimezone())
            counts["requirements"] += 1


def _import_company_matrix(sheet_name, rows, company, employees, requirements, types, names, counts, today):
    employee = employees.upsert(company.id, f"IMPORT-{company.code}-CORPORATIVO"[:64], full_name=f"{company.name} — Controle corporativo", source_row_identifier=f"{sheet_name}:corporativo")
    counts["employees"] += 1
    for row_index, row in enumerate(rows):
        for column_index, raw in enumerate(row):
            expiry = _parse_date(raw)
            if not expiry:
                continue
            column = _column_label(rows, row_index, column_index)
            line = _row_label(row, column_index)
            title = " — ".join(part for part in (sheet_name, column, line) if part) or f"{sheet_name}: célula {row_index + 1},{column_index + 1}"
            requirement_type = _ensure_type(title, types, employees.session)
            names.add(title)
            assessment = ExpirationPolicy.assess(expiry, today)
            requirements.synchronize(company_id=company.id, employee_id=employee.id, requirement_type_id=requirement_type.id, expiry_date=expiry, source_value=_text(raw), source_column=title[:255], calculated_status=assessment.status, last_synced_at=datetime.now().astimezone())
            counts["requirements"] += 1
