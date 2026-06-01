from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsItem
from app.models.options import OptionsChainRow as OptionsChainRowORM
from app.models.pipeline import PipelineRun
from app.models.stocks import DividendHistory, Price, Stock
from app.sources.base import (
    DividendEvent,
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
        from sqlalchemy import func

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
        from sqlalchemy import func

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
        from sqlalchemy import func, text

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
        from datetime import UTC, datetime as dt

        await self.session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=status,
                steps_completed=completed,
                errors=errors,
                finished_at=now or dt.now(tz=UTC),
            )
        )

    async def recent_runs(self, limit: int) -> list[PipelineRun]:
        rows = await self.session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def get_run(self, run_id: int) -> PipelineRun | None:
        return await self.session.get(PipelineRun, run_id)
