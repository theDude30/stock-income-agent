from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    dividend_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    signals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    passed_screen: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
