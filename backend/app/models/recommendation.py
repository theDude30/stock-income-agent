from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'superseded', 'executed')",
            name="ck_recommendations_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    signals_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    approval_mode: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
