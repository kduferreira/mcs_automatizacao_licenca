"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _id_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "companies",
        *_id_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("spreadsheet_id", sa.String(255), nullable=False),
        sa.Column("main_sheet_name", sa.String(255), nullable=False),
        sa.Column("history_sheet_name", sa.String(255), nullable=False),
        sa.Column("executions_sheet_name", sa.String(255), nullable=False),
        sa.Column("responsible_emails", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "employees",
        *_id_columns(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("automation_id", sa.String(64), nullable=False),
        sa.Column("source_row_identifier", sa.String(64)),
        sa.Column("unit", sa.String(255)),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("mobilizing_company", sa.String(255)),
        sa.Column("badge_id", sa.String(128)),
        sa.Column("cpf_protected", sa.String(255)),
        sa.Column("rg_protected", sa.String(255)),
        sa.Column("admission_date", sa.Date()),
        sa.Column("birth_date", sa.Date()),
        sa.Column("phone", sa.String(64)),
        sa.Column("email", sa.String(320)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "automation_id"),
    )
    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.create_table(
        "vehicles",
        *_id_columns(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id")),
        sa.Column("plate", sa.String(16)),
        sa.Column("brand", sa.String(128)),
        sa.Column("model", sa.String(128)),
        sa.Column("type", sa.String(128)),
        sa.Column("year", sa.Integer()),
        sa.Column("chassis", sa.String(128)),
        sa.Column("renavam", sa.String(64)),
        sa.Column("color", sa.String(64)),
        sa.Column("engine_specification", sa.String(255)),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_vehicles_company_id", "vehicles", ["company_id"])
    op.create_table(
        "requirement_types",
        *_id_columns(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("spreadsheet_header", sa.String(255)),
        sa.Column("status_header", sa.String(255)),
        sa.Column("expected_format", sa.String(64)),
        sa.Column("requires_expiry_date", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "notification_rules",
        *_id_columns(),
        sa.Column("days_before_expiry", sa.Integer()),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("template_code", sa.String(64), nullable=False),
        sa.Column("send_email", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "requirement_records",
        *_id_columns(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id")),
        sa.Column(
            "requirement_type_id", sa.Uuid(), sa.ForeignKey("requirement_types.id"), nullable=False
        ),
        sa.Column("completion_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("source_value", sa.String(255)),
        sa.Column("source_status", sa.String(255)),
        sa.Column("calculated_status", sa.String(32), nullable=False),
        sa.Column("source_column", sa.String(255)),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )
    for name, columns in (
        ("ix_requirement_records_company_expiry", ["company_id", "expiry_date"]),
        ("ix_requirement_records_employee", ["employee_id"]),
        ("ix_requirement_records_status", ["calculated_status"]),
        ("ix_requirement_records_type", ["requirement_type_id"]),
    ):
        op.create_index(name, "requirement_records", columns)
    op.create_table(
        "notification_events",
        *_id_columns(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column(
            "requirement_record_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_records.id"),
            nullable=False,
        ),
        sa.Column(
            "notification_rule_id",
            sa.Uuid(),
            sa.ForeignKey("notification_rules.id"),
            nullable=False,
        ),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("notification_key", sa.String(128), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("destination_masked", sa.String(320)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("notification_key"),
    )
    op.create_index("ix_notification_events_company_id", "notification_events", ["company_id"])
    op.create_table(
        "sync_executions",
        *_id_columns(),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id")),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("rows_read", sa.Integer(), nullable=False),
        sa.Column("employees_processed", sa.Integer(), nullable=False),
        sa.Column("requirements_processed", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("due_today_count", sa.Integer(), nullable=False),
        sa.Column("expired_count", sa.Integer(), nullable=False),
        sa.Column("emails_sent", sa.Integer(), nullable=False),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False),
        sa.Column("errors_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON()),
    )
    op.create_index("ix_sync_executions_company_id", "sync_executions", ["company_id"])


def downgrade() -> None:
    for table in (
        "sync_executions",
        "notification_events",
        "requirement_records",
        "notification_rules",
        "requirement_types",
        "vehicles",
        "employees",
        "companies",
    ):
        op.drop_table(table)
