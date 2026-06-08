"""analysis tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fundamentals",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("fiscal_period", sa.Text(), nullable=False),
        sa.Column("revenue", sa.Numeric(18, 2), nullable=True),
        sa.Column("eps", sa.Numeric(12, 4), nullable=True),
        sa.Column("fcf", sa.Numeric(18, 2), nullable=True),
        sa.Column("net_income", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_debt", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_equity", sa.Numeric(18, 2), nullable=True),
        sa.Column("dividends_paid", sa.Numeric(18, 2), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "fiscal_period"),
    )

    op.create_table(
        "screenings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("dividend_quality_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed_screen", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screenings_run_id", "screenings", ["run_id"])
    op.create_index("ix_screenings_ticker_created", "screenings", ["ticker", "created_at"])

    op.create_table(
        "dividend_safety_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("payout_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("fcf_coverage", sa.Numeric(8, 4), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(8, 4), nullable=True),
        sa.Column("consecutive_years_paid", sa.SmallInteger(), nullable=True),
        sa.Column("concerns", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("llm_reasoning", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("llm_prompt_version", sa.Text(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_safety_ticker_scored", "dividend_safety_scores", ["ticker", "scored_at"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("signals_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("llm_prompt_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("approval_mode", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'superseded', 'executed')",
            name="ck_recommendations_status",
        ),
    )
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index("ix_recommendations_run_id", "recommendations", ["run_id"])
    op.create_index("ix_recommendations_ticker_created", "recommendations", ["ticker", "created_at"])


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("dividend_safety_scores")
    op.drop_table("screenings")
    op.drop_table("fundamentals")
