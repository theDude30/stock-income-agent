from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("kind IN ('stock', 'short_call')", name="ck_positions_kind"),
        CheckConstraint(
            "status IN ('open', 'closed', 'assigned', 'expired')",
            name="ck_positions_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    recommendation_id: Mapped[int] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    strike: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(
            "side IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')",
            name="ck_trades_side",
        ),
        CheckConstraint(
            "reason IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')",
            name="ck_trades_reason",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    shares_or_contracts: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class IncomeEvent(Base):
    __tablename__ = "income_events"
    __table_args__ = (
        CheckConstraint(
            "type IN ('dividend', 'call_premium', 'assignment_gain')",
            name="ck_income_events_type",
        ),
        UniqueConstraint(
            "ticker", "event_date", "type", "source_position_id",
            name="uq_income_events_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_position_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=True)
    source_recommendation_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("outcome IN ('win', 'loss', 'breakeven')", name="ck_feedback_outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    capital_pnl: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    dividends_received: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=Decimal(0))
    premiums_collected: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=Decimal(0))
    total_return_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    held_days: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    exit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
