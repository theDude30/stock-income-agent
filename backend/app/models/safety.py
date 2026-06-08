from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DividendSafetyScore(Base):
    __tablename__ = "dividend_safety_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payout_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fcf_coverage: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    consecutive_years_paid: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    concerns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    llm_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    llm_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
