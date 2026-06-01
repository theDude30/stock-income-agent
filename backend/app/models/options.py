from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class OptionsChainRow(Base):
    __tablename__ = "options_chains"
    __table_args__ = (CheckConstraint("option_type IN ('call', 'put')", name="ck_options_chains_type"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    option_type: Mapped[str] = mapped_column(Text, nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    last: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
