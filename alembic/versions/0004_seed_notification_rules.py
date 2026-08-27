"""seed notification rules

Revision ID: 0004_seed_notification_rules
Revises: 0003_company_telegram_chat
"""

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "0004_seed_notification_rules"
down_revision = "0003_company_telegram_chat"
branch_labels = None
depends_on = None

RULES = (
    (30, "ALERTA_30_DIAS", "VERDE"),
    (21, "ALERTA_21_DIAS", "VERDE"),
    (14, "ALERTA_14_DIAS", "AMARELO"),
    (7, "ALERTA_7_DIAS", "VERMELHO"),
    (3, "ALERTA_3_DIAS", "VERMELHO"),
    (1, "ALERTA_1_DIA", "CRITICO"),
    (0, "VENCE_HOJE", "CRITICO"),
    (None, "VENCIDO", "CRITICO"),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing_codes = {
        row[0]
        for row in connection.execute(sa.text("SELECT code FROM notification_rules"))
    }
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(),
            "created_at": now,
            "updated_at": now,
            "days_before_expiry": days,
            "code": code,
            "severity": severity,
            "enabled": True,
            "template_code": code,
            "send_email": True,
        }
        for days, code, severity in RULES
        if code not in existing_codes
    ]
    if rows:
        op.bulk_insert(
            sa.table(
                "notification_rules",
                sa.column("id", sa.Uuid()),
                sa.column("created_at", sa.DateTime(timezone=True)),
                sa.column("updated_at", sa.DateTime(timezone=True)),
                sa.column("days_before_expiry", sa.Integer()),
                sa.column("code", sa.String()),
                sa.column("severity", sa.String()),
                sa.column("enabled", sa.Boolean()),
                sa.column("template_code", sa.String()),
                sa.column("send_email", sa.Boolean()),
            ),
            rows,
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for _, code, _ in RULES)
    op.execute(sa.text(f"DELETE FROM notification_rules WHERE code IN ({codes})"))
