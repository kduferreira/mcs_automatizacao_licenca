from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.security import require_api_key
from app.application.dto.schemas import (
    CompanyResponse,
    DashboardCompanyResponse,
    ExpirationResponse,
    NotificationResponse,
)
from app.domain.rules.expiration import ExpirationPolicy
from app.infrastructure.database.models import (
    Company,
    Employee,
    NotificationEvent,
    RequirementRecord,
    RequirementType,
)
from app.infrastructure.database.session import get_session

router = APIRouter(
    prefix="/api/v1/companies", tags=["companies"], dependencies=[Depends(require_api_key)]
)


@router.get("/dashboard", response_model=list[DashboardCompanyResponse])
def dashboard(session: Session = Depends(get_session)):
    companies = list(session.scalars(select(Company).order_by(Company.code)))
    today = date.today()
    response = []
    for company in companies:
        expirations, due_today, expired = session.execute(
            select(
                func.count(RequirementRecord.id),
                func.count(RequirementRecord.id).filter(RequirementRecord.expiry_date == today),
                func.count(RequirementRecord.id).filter(RequirementRecord.expiry_date < today),
            ).where(
                RequirementRecord.company_id == company.id,
                RequirementRecord.active.is_(True),
            )
        ).one()
        pending = session.scalar(
            select(func.count(NotificationEvent.id)).where(
                NotificationEvent.company_id == company.id,
                NotificationEvent.status.in_(("PENDING", "FAILED")),
            )
        )
        response.append(
            DashboardCompanyResponse(
                id=company.id,
                name=company.name,
                code=company.code,
                active=company.active,
                expirations=expirations,
                due_today=due_today,
                expired=expired,
                notifications_pending=pending or 0,
            )
        )
    return response


@router.get("", response_model=list[CompanyResponse])
def list_companies(session: Session = Depends(get_session)):
    return list(session.scalars(select(Company).order_by(Company.code)))


@router.get("/{company_id}/expirations", response_model=list[ExpirationResponse])
def expirations(
    company_id: uuid.UUID,
    days: int | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
):
    if not session.get(Company, company_id):
        raise HTTPException(404, "Empresa não encontrada")
    rows = session.execute(
        select(RequirementRecord, Employee, RequirementType)
        .join(Employee)
        .join(RequirementType)
        .where(RequirementRecord.company_id == company_id, RequirementRecord.active.is_(True))
    ).all()
    result = []
    for record, employee, item in rows:
        assessment = ExpirationPolicy.assess(record.expiry_date, date.today())
        if days is not None and (
            assessment.days_remaining is None or assessment.days_remaining > days
        ):
            continue
        result.append(
            ExpirationResponse(
                requirement_record_id=record.id,
                employee_id=employee.id,
                employee_name=employee.full_name,
                item=item.name,
                expiry_date=record.expiry_date,
                days_remaining=assessment.days_remaining,
                status=record.calculated_status,
            )
        )
    return result


@router.get("/{company_id}/notifications", response_model=list[NotificationResponse])
def notifications(company_id: uuid.UUID, session: Session = Depends(get_session)):
    if not session.get(Company, company_id):
        raise HTTPException(404, "Empresa não encontrada")
    return list(
        session.scalars(
            select(NotificationEvent)
            .where(NotificationEvent.company_id == company_id)
            .order_by(NotificationEvent.created_at.desc())
        )
    )
