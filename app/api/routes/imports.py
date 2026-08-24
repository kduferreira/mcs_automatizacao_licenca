from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

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
    "ID_AUTOMACAO",
    "NOME_COMPLETO",
    "UNIDADE",
    "E_MAIL",
    "EMAIL",
    "CPF",
    "RG",
    "TELEFONE",
    "CELULAR",
    "CARGO",
    "FUNCAO",
    "DATA_ADMISSAO",
    "DATA_NASCIMENTO",
    "NASCIMENTO",
}


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
    clean = re.sub(r"[^A-Z0-9_]", "", normalize_header(header))[:82]
    return f"IMPORT_{clean or 'ITEM'}"


@router.post("/spreadsheet", response_model=SpreadsheetImportResponse, status_code=status.HTTP_201_CREATED)
def import_spreadsheet(
    payload: SpreadsheetImportRequest, session: Session = Depends(get_session)
):
    try:
        mapper = SheetMapper(payload.rows)
        mapper.require("NOME COMPLETO")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    company = session.scalar(select(Company).where(Company.code == payload.company_code))
    if company is None:
        company = Company(
            name=payload.company_name,
            code=payload.company_code,
            spreadsheet_id=f"{LOCAL_UPLOAD_PREFIX}{payload.company_code}",
            responsible_emails=payload.responsible_emails,
        )
        session.add(company)
        session.flush()
    else:
        company.name = payload.company_name
        company.responsible_emails = payload.responsible_emails
        company.active = True

    active_types = list(
        session.scalars(select(RequirementType).where(RequirementType.active.is_(True)))
    )
    types_by_header = {
        normalize_header(item.spreadsheet_header or ""): item
        for item in active_types
        if item.spreadsheet_header
    }
    date_columns: dict[str, RequirementType] = {}
    for header, index in mapper.headers.items():
        if header in IDENTITY_HEADERS:
            continue
        values = [row[index] for row in mapper.rows if index < len(row) and str(row[index]).strip()]
        if not values:
            continue
        valid_dates = 0
        for value in values:
            try:
                valid_dates += parse_sheet_date(value) is not None
            except ValueError:
                continue
        if not valid_dates:
            continue
        requirement_type = types_by_header.get(header)
        if requirement_type is None:
            code = _new_requirement_code(header)
            requirement_type = session.scalar(select(RequirementType).where(RequirementType.code == code))
            if requirement_type is None:
                requirement_type = RequirementType(
                    code=code,
                    name=mapper.original_headers[index],
                    category=_category(header),
                    spreadsheet_header=mapper.original_headers[index],
                )
                session.add(requirement_type)
                session.flush()
            types_by_header[header] = requirement_type
        date_columns[header] = requirement_type

    if not date_columns:
        raise HTTPException(
            422,
            "Nenhuma coluna de vencimento foi encontrada. Inclua ao menos uma coluna com datas válidas.",
        )

    employees = SQLAlchemyEmployeeRepository(session)
    requirements = SQLAlchemyRequirementRepository(session)
    counts: Counter[str] = Counter()
    today = datetime.now().date()
    automation_column = mapper.headers.get("ID_AUTOMACAO")
    for mapped_row in mapper.mapped_rows():
        name = str(mapped_row.values.get("NOME_COMPLETO") or "").strip()
        if not name:
            counts["invalid_rows"] += 1
            continue
        automation_id = mapped_row.automation_id
        if automation_column is None:
            automation_id = f"IMPORT-{company.code}-{mapped_row.row_number}"[:64]
        employee = employees.upsert(
            company.id,
            automation_id,
            full_name=name,
            unit=_text(mapped_row.values.get("UNIDADE")),
            email=_text(mapped_row.values.get("E_MAIL") or mapped_row.values.get("EMAIL")),
            source_row_identifier=str(mapped_row.row_number),
        )
        counts["employees"] += 1
        for header, requirement_type in date_columns.items():
            raw = mapped_row.values.get(header)
            try:
                expiry = parse_sheet_date(raw)
            except ValueError:
                if _text(raw):
                    counts["invalid_dates"] += 1
                continue
            if expiry is None:
                continue
            assessment = ExpirationPolicy.assess(expiry, today)
            requirements.synchronize(
                company_id=company.id,
                employee_id=employee.id,
                requirement_type_id=requirement_type.id,
                expiry_date=expiry,
                source_value=_text(raw),
                source_column=requirement_type.spreadsheet_header,
                calculated_status=assessment.status,
                last_synced_at=datetime.now().astimezone(),
            )
            counts["requirements"] += 1
    session.commit()
    return SpreadsheetImportResponse(
        company=company,
        employees_imported=counts["employees"],
        requirements_imported=counts["requirements"],
        date_columns=[item.name for item in date_columns.values()],
        invalid_rows=counts["invalid_rows"],
        invalid_dates=counts["invalid_dates"],
    )


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
