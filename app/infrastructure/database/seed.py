from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import Company, NotificationRule, RequirementType

REQUIREMENTS = [
    ("CNH", "Validade da CNH", "DOCUMENT", "VALIDADE DA CNH"),
    ("ASO", "ASO", "ASO", "ASO"),
    ("NR_17", "NR-17", "TRAINING", "NR 17"),
    ("NR_06", "NR-06", "TRAINING", "NR 06"),
    ("NR_23", "NR-23", "TRAINING", "NR 23"),
    ("RAC_02", "RAC 02", "AMBIENTATION", "RAC 02"),
    ("FEBRE_AMARELA", "Febre amarela", "VACCINE", "FEBRE AMARELA"),
    ("ART", "Validade da ART", "VEHICLE", "VALIDADE DA ART"),
    ("SELO_ENEVA", "Validade selo Eneva", "MOBILIZATION", "VALIDADE SELO ENEVA"),
]
RULES = [
    (30, "ALERTA_30_DIAS", "VERDE"),
    (21, "ALERTA_21_DIAS", "VERDE"),
    (14, "ALERTA_14_DIAS", "AMARELO"),
    (7, "ALERTA_7_DIAS", "VERMELHO"),
    (3, "ALERTA_3_DIAS", "VERMELHO"),
    (1, "ALERTA_1_DIA", "CRITICO"),
    (0, "VENCE_HOJE", "CRITICO"),
    (None, "VENCIDO", "CRITICO"),
]


def seed(session: Session) -> None:
    for code, name, category, header in REQUIREMENTS:
        if not session.scalar(select(RequirementType).where(RequirementType.code == code)):
            session.add(
                RequirementType(code=code, name=name, category=category, spreadsheet_header=header)
            )
    for days, code, severity in RULES:
        if not session.scalar(select(NotificationRule).where(NotificationRule.code == code)):
            session.add(
                NotificationRule(
                    days_before_expiry=days, code=code, severity=severity, template_code=code
                )
            )
    for code in ("EMPRESA_A", "EMPRESA_B", "EMPRESA_C"):
        if not session.scalar(select(Company).where(Company.code == code)):
            session.add(
                Company(
                    name=code.replace("_", " ").title(),
                    code=code,
                    spreadsheet_id=f"CONFIGURE-{code}",
                    responsible_emails=[],
                )
            )
    session.commit()


if __name__ == "__main__":
    from app.infrastructure.database.session import SessionLocal

    with SessionLocal() as session:
        seed(session)
