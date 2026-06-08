import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class OptionsStep(Step):
    name = "options"
    is_critical = False

    def __init__(
        self,
        watchlist_size: int = 50,
        expirations_within_days: int = 60,
        concurrency: int = 10,
        attempts: int = 3,
    ) -> None:
        self.watchlist_size = watchlist_size
        self.expirations_within_days = expirations_within_days
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        # Prefer the screener's dividend_quality_score ranking; fall back to the
        # trailing-12mo yield proxy when no screening run has completed yet.
        run_id = await ctx.repo.latest_screening_run_id()
        if run_id is not None:
            watchlist = await ctx.repo.top_screened_tickers(run_id, limit=self.watchlist_size)
        else:
            watchlist = await ctx.repo.top_tickers_by_ttm_yield(limit=self.watchlist_size, today=today)
        # Held tickers always included. None for now; placeholder for Sub-project 4.
        held: list[str] = []
        tickers = list(dict.fromkeys(list(watchlist) + held))  # preserve order, dedupe
        if not tickers:
            return StepResult()

        sem = asyncio.Semaphore(self.concurrency)
        snapshot_at = ctx.now()

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    rows = await _retry(
                        lambda: list(
                            ctx.sources.options.fetch(ticker, self.expirations_within_days)
                        ),
                        attempts=self.attempts,
                    )
                    await ctx.repo.insert_options_snapshot(ticker, rows, snapshot_at)
                    return ticker, None
                except Exception as e:
                    logger.warning("options: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
