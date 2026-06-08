from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fundamentals import Fundamentals
from app.models.news import NewsItem
from app.models.options import OptionsChainRow as OptionsChainRowORM
from app.models.pipeline import PipelineRun
from app.models.recommendation import Recommendation
from app.models.safety import DividendSafetyScore
from app.models.screening import Screening
from app.models.stocks import DividendHistory, Price, Stock
from app.sources.base import (
    DividendEvent,
    FundamentalsSnapshot,
    NewsItemDTO,
    OptionsChainRow,
    PriceBar,
    StockMeta,
)


class PipelineRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- stocks -----

    async def upsert_stocks(self, stocks: Iterable[StockMeta], today: date) -> None:
        incoming = list(stocks)
        incoming_tickers = {s.ticker for s in incoming}
        for s in incoming:
            stmt = pg_insert(Stock).values(
                ticker=s.ticker,
                name=s.name,
                sector=s.sector,
                industry=s.industry,
                active=True,
                added_at=today,
                removed_at=None,
            ).on_conflict_do_update(
                index_elements=[Stock.ticker],
                set_={
                    "name": s.name,
                    "sector": s.sector,
                    "industry": s.industry,
                    "active": True,
                    "removed_at": None,
                },
            )
            await self.session.execute(stmt)

        # Deactivate anything no longer present
        if incoming_tickers:
            await self.session.execute(
                update(Stock)
                .where(Stock.ticker.notin_(incoming_tickers))
                .where(Stock.active.is_(True))
                .values(active=False, removed_at=today)
            )

    async def list_active_tickers(self) -> list[str]:
        rows = await self.session.execute(select(Stock.ticker).where(Stock.active.is_(True)).order_by(Stock.ticker))
        return [r[0] for r in rows.all()]

    # ----- prices -----

    async def upsert_prices(self, ticker: str, bars: Iterable[PriceBar]) -> int:
        bars = list(bars)
        if not bars:
            return 0
        values = [
            {
                "ticker": ticker,
                "date": b.date,
                "open": Decimal(str(b.open)),
                "high": Decimal(str(b.high)),
                "low": Decimal(str(b.low)),
                "close": Decimal(str(b.close)),
                "adj_close": Decimal(str(b.adj_close)),
                "volume": b.volume,
            }
            for b in bars
        ]
        stmt = pg_insert(Price).values(values).on_conflict_do_update(
            index_elements=[Price.ticker, Price.date],
            set_={
                "open": pg_insert(Price).excluded.open,
                "high": pg_insert(Price).excluded.high,
                "low": pg_insert(Price).excluded.low,
                "close": pg_insert(Price).excluded.close,
                "adj_close": pg_insert(Price).excluded.adj_close,
                "volume": pg_insert(Price).excluded.volume,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def last_price_date(self, ticker: str) -> date | None:
        row = await self.session.execute(
            select(func.max(Price.date)).where(Price.ticker == ticker)
        )
        return row.scalar()

    # ----- dividends -----

    async def upsert_dividends(self, ticker: str, events: Iterable[DividendEvent]) -> int:
        events = list(events)
        if not events:
            return 0
        values = [
            {
                "ticker": ticker,
                "ex_date": e.ex_date,
                "pay_date": e.pay_date,
                "amount_per_share": Decimal(str(e.amount_per_share)),
            }
            for e in events
        ]
        stmt = pg_insert(DividendHistory).values(values).on_conflict_do_update(
            index_elements=[DividendHistory.ticker, DividendHistory.ex_date],
            set_={
                "pay_date": pg_insert(DividendHistory).excluded.pay_date,
                "amount_per_share": pg_insert(DividendHistory).excluded.amount_per_share,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def last_dividend_ex_date(self, ticker: str) -> date | None:
        row = await self.session.execute(
            select(func.max(DividendHistory.ex_date)).where(DividendHistory.ticker == ticker)
        )
        return row.scalar()

    # ----- options (insert-only, daily snapshot) -----

    async def insert_options_snapshot(
        self, ticker: str, rows: Iterable[OptionsChainRow], snapshot_at: datetime
    ) -> int:
        rows = list(rows)
        if not rows:
            return 0
        values = [
            {
                "ticker": ticker,
                "expiration_date": r.expiration_date,
                "strike": Decimal(str(r.strike)),
                "option_type": r.option_type,
                "bid": Decimal(str(r.bid)) if r.bid is not None else None,
                "ask": Decimal(str(r.ask)) if r.ask is not None else None,
                "last": Decimal(str(r.last)) if r.last is not None else None,
                "implied_volatility": (
                    Decimal(str(r.implied_volatility)) if r.implied_volatility is not None else None
                ),
                "volume": r.volume,
                "open_interest": r.open_interest,
                "snapshot_at": snapshot_at,
            }
            for r in rows
        ]
        await self.session.execute(pg_insert(OptionsChainRowORM).values(values))
        return len(values)

    # ----- news -----

    async def insert_news(self, ticker: str, items: Iterable[NewsItemDTO]) -> int:
        items = list(items)
        if not items:
            return 0
        values = [
            {
                "ticker": ticker,
                "published_at": n.published_at,
                "source": n.source,
                "url": n.url,
                "title": n.title,
                "summary": n.summary,
            }
            for n in items
        ]
        stmt = pg_insert(NewsItem).values(values).on_conflict_do_nothing(index_elements=[NewsItem.url])
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    # ----- yields (for options watchlist; T12M dividend / latest close) -----

    async def top_tickers_by_ttm_yield(self, limit: int, today: date) -> list[str]:
        """Trailing-12-month dividends divided by latest close. Used as a v1 watchlist proxy
        until Sub-project 3's screener provides a real ranking."""
        one_year_ago = (
            date(today.year - 1, today.month, today.day)
            if not (today.month == 2 and today.day == 29)
            else date(today.year - 1, 2, 28)
        )
        # latest close per ticker
        latest_close_subq = (
            select(Price.ticker, func.max(Price.date).label("max_date"))
            .group_by(Price.ticker)
            .subquery()
        )
        ttm_div_subq = (
            select(
                DividendHistory.ticker,
                func.sum(DividendHistory.amount_per_share).label("ttm"),
            )
            .where(DividendHistory.ex_date >= one_year_ago)
            .group_by(DividendHistory.ticker)
            .subquery()
        )
        stmt = (
            select(
                Stock.ticker,
                (ttm_div_subq.c.ttm / Price.close).label("yield_pct"),
            )
            .join(latest_close_subq, latest_close_subq.c.ticker == Stock.ticker)
            .join(Price, (Price.ticker == latest_close_subq.c.ticker) & (Price.date == latest_close_subq.c.max_date))
            .join(ttm_div_subq, ttm_div_subq.c.ticker == Stock.ticker)
            .where(Stock.active.is_(True))
            .order_by(text("yield_pct DESC"))
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [r[0] for r in rows.all()]

    # ----- pipeline_runs -----

    async def start_run(self, now: datetime) -> int:
        run = PipelineRun(started_at=now, status="running", steps_completed=[], errors={})
        self.session.add(run)
        await self.session.flush()
        return run.id

    async def finish_run(
        self,
        run_id: int,
        status: str,
        completed: list[str],
        errors: dict,
        now: datetime | None = None,
    ) -> None:
        await self.session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=status,
                steps_completed=completed,
                errors=errors,
                finished_at=now or datetime.now(tz=UTC),
            )
        )

    async def recent_runs(self, limit: int) -> list[PipelineRun]:
        rows = await self.session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def get_run(self, run_id: int) -> PipelineRun | None:
        return await self.session.get(PipelineRun, run_id)

    # ----- fundamentals -----

    async def upsert_fundamentals(self, ticker: str, snaps: Iterable[FundamentalsSnapshot]) -> int:
        snaps = list(snaps)
        if not snaps:
            return 0
        now = datetime.now(tz=UTC)

        def dec(x):
            return Decimal(str(x)) if x is not None else None

        values = [
            {
                "ticker": ticker, "fiscal_period": s.fiscal_period,
                "revenue": dec(s.revenue), "eps": dec(s.eps), "fcf": dec(s.fcf),
                "net_income": dec(s.net_income), "total_debt": dec(s.total_debt),
                "total_equity": dec(s.total_equity), "dividends_paid": dec(s.dividends_paid),
                "snapshot_at": now,
            }
            for s in snaps
        ]
        stmt = pg_insert(Fundamentals).values(values).on_conflict_do_update(
            index_elements=[Fundamentals.ticker, Fundamentals.fiscal_period],
            set_={
                "revenue": pg_insert(Fundamentals).excluded.revenue,
                "eps": pg_insert(Fundamentals).excluded.eps,
                "fcf": pg_insert(Fundamentals).excluded.fcf,
                "net_income": pg_insert(Fundamentals).excluded.net_income,
                "total_debt": pg_insert(Fundamentals).excluded.total_debt,
                "total_equity": pg_insert(Fundamentals).excluded.total_equity,
                "dividends_paid": pg_insert(Fundamentals).excluded.dividends_paid,
                "snapshot_at": pg_insert(Fundamentals).excluded.snapshot_at,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def latest_fundamentals(self, ticker: str) -> Fundamentals | None:
        row = await self.session.execute(
            select(Fundamentals).where(Fundamentals.ticker == ticker)
            .order_by(Fundamentals.fiscal_period.desc()).limit(1)
        )
        return row.scalar_one_or_none()

    async def fundamentals_history(self, ticker: str, limit: int = 8) -> list[Fundamentals]:
        rows = await self.session.execute(
            select(Fundamentals).where(Fundamentals.ticker == ticker)
            .order_by(Fundamentals.fiscal_period.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    # ----- screenings -----

    async def insert_screening(self, run_id, ticker, score, signals, passed, now) -> None:
        self.session.add(Screening(
            run_id=run_id, ticker=ticker, dividend_quality_score=Decimal(str(score)),
            signals=signals, passed_screen=passed, created_at=now,
        ))
        await self.session.flush()

    async def get_screenings(self, run_id: int) -> list[Screening]:
        rows = await self.session.execute(
            select(Screening).where(Screening.run_id == run_id)
            .order_by(Screening.dividend_quality_score.desc())
        )
        return list(rows.scalars().all())

    async def top_screened_tickers(self, run_id: int, limit: int) -> list[str]:
        rows = await self.session.execute(
            select(Screening.ticker).where(Screening.run_id == run_id)
            .order_by(Screening.dividend_quality_score.desc()).limit(limit)
        )
        return [r[0] for r in rows.all()]

    async def latest_screening_run_id(self) -> int | None:
        row = await self.session.execute(select(func.max(Screening.run_id)))
        return row.scalar()

    # ----- safety scores -----

    async def insert_safety_score(self, ticker, score, payout_ratio, fcf_coverage,
                                  debt_to_equity, consecutive_years_paid, concerns,
                                  reasoning, model, prompt_version, now) -> None:
        def dec(x):
            return Decimal(str(x)) if x is not None else None

        self.session.add(DividendSafetyScore(
            ticker=ticker, score=score, payout_ratio=dec(payout_ratio),
            fcf_coverage=dec(fcf_coverage), debt_to_equity=dec(debt_to_equity),
            consecutive_years_paid=consecutive_years_paid, concerns=list(concerns),
            llm_reasoning=reasoning, llm_model=model, llm_prompt_version=prompt_version,
            scored_at=now,
        ))
        await self.session.flush()

    async def latest_safety_score(self, ticker: str) -> DividendSafetyScore | None:
        row = await self.session.execute(
            select(DividendSafetyScore).where(DividendSafetyScore.ticker == ticker)
            .order_by(DividendSafetyScore.scored_at.desc()).limit(1)
        )
        return row.scalar_one_or_none()

    # ----- recommendations -----

    async def insert_recommendation(self, run_id, type, ticker, confidence, payload,
                                    reasoning, signals_snapshot, model, prompt_version, now) -> int:
        rec = Recommendation(
            run_id=run_id, type=type, ticker=ticker, confidence=confidence, payload=payload,
            reasoning=reasoning, signals_snapshot=signals_snapshot, llm_model=model,
            llm_prompt_version=prompt_version, status="pending", approval_mode="manual",
            created_at=now,
        )
        self.session.add(rec)
        await self.session.flush()
        return rec.id

    async def list_recommendations(self, status: str | None, type_: str | None) -> list[Recommendation]:
        stmt = select(Recommendation)
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        if type_ is not None:
            stmt = stmt.where(Recommendation.type == type_)
        stmt = stmt.order_by(Recommendation.created_at.desc())
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_recommendation(self, rec_id: int) -> Recommendation | None:
        return await self.session.get(Recommendation, rec_id)

    async def set_recommendation_status(self, rec_id, status, decided_by, now,
                                        reject_reason: str | None = None) -> bool:
        rec = await self.session.get(Recommendation, rec_id)
        if rec is None or rec.status != "pending":
            return False
        rec.status = status
        rec.decided_by = decided_by
        rec.decided_at = now
        if reject_reason is not None:
            payload = dict(rec.payload or {})
            payload["reject_reason"] = reject_reason
            rec.payload = payload
        await self.session.flush()
        return True

    # ----- LLM cost bookkeeping -----

    async def add_llm_usage(self, run_id: int, tokens: int, cost: float) -> None:
        await self.session.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(
                llm_tokens_used=func.coalesce(PipelineRun.llm_tokens_used, 0) + tokens,
                llm_cost_usd=func.coalesce(PipelineRun.llm_cost_usd, 0) + Decimal(str(cost)),
            )
        )
