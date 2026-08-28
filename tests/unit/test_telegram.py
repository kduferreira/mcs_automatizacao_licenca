from datetime import date
from types import SimpleNamespace

from app.application.services.execution import ExecutionService
from app.infrastructure.telegram.gateway import TelegramGateway


def test_telegram_summary_groups_items_by_expiry_date():
    message = ExecutionService._telegram_message(
        SimpleNamespace(name="Empresa Teste"),
        {
            "status": "SUCCESS",
            "employees_processed": 2,
            "due_today": 0,
            "expired": 1,
            "emails_sent": 1,
            "errors": 0,
        },
        [
            {
                "employee_name": "Ana",
                "requirement_type": "ASO",
                "expiry_date": date(2026, 8, 28),
                "days_remaining": 1,
            },
            {
                "employee_name": "Bruno",
                "requirement_type": "NR-17",
                "expiry_date": date(2026, 8, 28),
                "days_remaining": 1,
            },
            {
                "employee_name": "Carla",
                "requirement_type": "Validade da CNH",
                "expiry_date": date(2026, 8, 26),
                "days_remaining": -1,
            },
        ],
    )

    assert "Vencem em 28/08/2026 (faltam 1 dia) — 2 item(ns)" in message
    assert "Ana — ASO (faltam 1 dia)" in message
    assert "Bruno — NR-17 (faltam 1 dia)" in message
    assert "Vencidos em 26/08/2026 (há 1 dia) — 1 item(ns)" in message
    assert "Carla — Validade da CNH (vencido há 1 dia)" in message


def test_telegram_message_parts_preserve_large_batch():
    message = ("Colaborador com vencimento\n" * 220) + "fim"

    parts = TelegramGateway._message_parts(message)

    assert len(parts) > 1
    assert all(len(part) <= TelegramGateway.max_message_length for part in parts)
    assert "".join(parts) == message
