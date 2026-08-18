from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.domain.enums.core import CalculatedStatus


@dataclass(frozen=True)
class ExpirationAssessment:
    expiry_date: date | None
    days_remaining: int | None
    status: CalculatedStatus


class ExpirationPolicy:
    """Regra pura; integrações e banco não participam do cálculo."""

    @staticmethod
    def assess(expiry_date: date | None, today: date) -> ExpirationAssessment:
        if expiry_date is None:
            return ExpirationAssessment(None, None, CalculatedStatus.SEM_DATA)
        days = (expiry_date - today).days
        if days > 21:
            status = CalculatedStatus.REGULAR if days > 30 else CalculatedStatus.ALERTA_VERDE
        elif days >= 15:
            status = CalculatedStatus.ALERTA_VERDE
        elif days >= 8:
            status = CalculatedStatus.ALERTA_AMARELO
        elif days >= 1:
            status = CalculatedStatus.ALERTA_VERMELHO
        elif days == 0:
            status = CalculatedStatus.VENCE_HOJE
        else:
            status = CalculatedStatus.VENCIDO
        return ExpirationAssessment(expiry_date, days, status)

    @staticmethod
    def choose_notification_rule(
        days_remaining: int | None, sent_days: set[int | None]
    ) -> int | None:
        """Seleciona somente o aviso pendente mais urgente aplicável.

        ``None`` representa a regra de vencido. Em execução atrasada, nenhuma
        sequência antiga é enviada: escolhe-se a régua mais urgente disponível.
        """
        if days_remaining is None:
            return None
        if days_remaining < 0:
            return None if None not in sent_days else None
        thresholds = (30, 21, 14, 7, 3, 1, 0)
        applicable = [threshold for threshold in thresholds if days_remaining <= threshold]
        for threshold in reversed(applicable):
            if threshold not in sent_days:
                return threshold
        return None
