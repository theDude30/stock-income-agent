import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class NewsStep(Step):
    name = "news"
    is_critical = False

    def __init__(self, watchlist_size: int = 50, concurrency: int = 10, attempts: int = 2) -> None:
        self.watchlist_size = watchlist_size
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        watchlist = await ctx.repo.top_tickers_by_ttm_yield(
            limit=self.watchlist_size, today=today
        )
        held: list[str] = []
        tickers = list(dict.fromkeys(list(watchlist) + held))
        if not tickers:
            return StepResult()

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    items = await _retry(
                        lambda: list(ctx.sources.news.fetch(ticker, None)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.insert_news(ticker, items)
                    return ticker, None
                except Exception as e:
                    logger.warning("news: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
