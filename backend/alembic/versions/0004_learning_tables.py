"""learning tables: agent_lessons, alerts

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_lessons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("evidence_recommendation_ids", postgresql.ARRAY(sa.Integer()),
                  nullable=False, server_default=sa.text("'{}'::integer[]")),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retired_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger(),
                  sa.ForeignKey("pipeline_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('new_recommendations', 'dividend_safety_alert', "
            "'dividend_payment_upcoming', 'position_closed', 'call_expiring', 'monthly_summary')",
            name="ck_alerts_type",
        ),
        sa.CheckConstraint("channel IN ('email', 'web')", name="ck_alerts_channel"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("agent_lessons")
