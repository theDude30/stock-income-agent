"""portfolio tables: positions, trades, income_events, feedback

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("shares", sa.Numeric(), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(), nullable=False),
        sa.Column("strike", sa.Numeric(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('stock', 'short_call')", name="ck_positions_kind"),
        sa.CheckConstraint("status IN ('open', 'closed', 'assigned', 'expired')", name="ck_positions_status"),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("shares_or_contracts", sa.Numeric(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "side IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')",
            name="ck_trades_side",
        ),
        sa.CheckConstraint(
            "reason IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')",
            name="ck_trades_reason",
        ),
    )
    op.create_table(
        "income_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("source_position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('dividend', 'call_premium', 'assignment_gain')",
            name="ck_income_events_type",
        ),
        sa.UniqueConstraint(
            "ticker", "event_date", "type", "source_position_id",
            name="uq_income_events_dedup",
        ),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_price", sa.Numeric(), nullable=False),
        sa.Column("exit_price", sa.Numeric(), nullable=True),
        sa.Column("capital_pnl", sa.Numeric(), nullable=False),
        sa.Column("dividends_received", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("premiums_collected", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("total_return_pct", sa.Numeric(), nullable=False),
        sa.Column("held_days", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('win', 'loss', 'breakeven')", name="ck_feedback_outcome"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("income_events")
    op.drop_table("trades")
    op.drop_table("positions")
