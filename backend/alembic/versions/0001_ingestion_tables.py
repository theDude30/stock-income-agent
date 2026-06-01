"""ingestion tables

Revision ID: 0001
Revises:
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("ticker", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_at", sa.Date(), nullable=False),
        sa.Column("removed_at", sa.Date(), nullable=True),
    )
    op.create_index("ix_stocks_active", "stocks", ["active"])

    op.create_table(
        "prices",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("adj_close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "date"),
    )
    op.create_index("ix_prices_date", "prices", ["date"])

    op.create_table(
        "dividend_history",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("amount_per_share", sa.Numeric(12, 6), nullable=False),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("ticker", "ex_date"),
    )

    op.create_table(
        "options_chains",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("strike", sa.Numeric(10, 2), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("bid", sa.Numeric(10, 4), nullable=True),
        sa.Column("ask", sa.Numeric(10, 4), nullable=True),
        sa.Column("last", sa.Numeric(10, 4), nullable=True),
        sa.Column("implied_volatility", sa.Numeric(8, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("option_type IN ('call', 'put')", name="ck_options_chains_type"),
    )
    op.create_index("ix_options_chains_ticker_snapshot", "options_chains", ["ticker", "snapshot_at"])
    op.create_index(
        "ix_options_chains_ticker_exp_strike_type",
        "options_chains",
        ["ticker", "expiration_date", "strike", "option_type"],
    )

    op.create_table(
        "news_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_news_items_ticker_published", "news_items", ["ticker", sa.text("published_at DESC")])

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("steps_completed", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("llm_tokens_used", sa.Integer(), nullable=True),
        sa.Column("llm_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_pipeline_runs_status",
        ),
    )
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", [sa.text("started_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_index("ix_news_items_ticker_published", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_options_chains_ticker_exp_strike_type", table_name="options_chains")
    op.drop_index("ix_options_chains_ticker_snapshot", table_name="options_chains")
    op.drop_table("options_chains")
    op.drop_table("dividend_history")
    op.drop_index("ix_prices_date", table_name="prices")
    op.drop_table("prices")
    op.drop_index("ix_stocks_active", table_name="stocks")
    op.drop_table("stocks")
