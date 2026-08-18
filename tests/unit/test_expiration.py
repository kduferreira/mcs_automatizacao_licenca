from datetime import date

import pytest

from app.domain.enums.core import CalculatedStatus
from app.domain.rules.expiration import ExpirationPolicy


@pytest.mark.parametrize(
    ("days", "status"),
    [
        (31, CalculatedStatus.REGULAR),
        (30, CalculatedStatus.ALERTA_VERDE),
        (21, CalculatedStatus.ALERTA_VERDE),
        (14, CalculatedStatus.ALERTA_AMARELO),
        (7, CalculatedStatus.ALERTA_VERMELHO),
        (3, CalculatedStatus.ALERTA_VERMELHO),
        (1, CalculatedStatus.ALERTA_VERMELHO),
        (0, CalculatedStatus.VENCE_HOJE),
        (-1, CalculatedStatus.VENCIDO),
    ],
)
def test_expiration_status(days, status):
    today = date(2026, 8, 17)
    assessment = ExpirationPolicy.assess(date.fromordinal(today.toordinal() + days), today)
    assert assessment.days_remaining == days
    assert assessment.status == status


def test_empty_date():
    assert ExpirationPolicy.assess(None, date.today()).status == CalculatedStatus.SEM_DATA


def test_delayed_execution_only_selects_most_urgent_pending_rule():
    assert ExpirationPolicy.choose_notification_rule(6, set()) == 7
    assert ExpirationPolicy.choose_notification_rule(2, {7}) == 3


def test_leap_year():
    assert ExpirationPolicy.assess(date(2028, 2, 29), date(2028, 2, 28)).days_remaining == 1
