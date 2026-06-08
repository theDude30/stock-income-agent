from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, PrimaryKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (PrimaryKeyConstraint("ticker", "fiscal_period"),)

    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    fiscal_period: Mapped[str] = mapped_column(Text)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    fcf: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    dividends_paid: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
