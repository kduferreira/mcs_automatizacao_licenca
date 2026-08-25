"""message templates

Revision ID: 0002_message_templates
Revises: 0001_initial_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_message_templates"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
    )


def downgrade() -> None:
    op.drop_table("message_templates")
