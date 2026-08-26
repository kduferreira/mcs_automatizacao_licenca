"""company telegram chat

Revision ID: 0003_company_telegram_chat
Revises: 0002_message_templates
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_company_telegram_chat"
down_revision = "0002_message_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("telegram_chat_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "telegram_chat_id")
