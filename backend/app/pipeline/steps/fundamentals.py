import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class FundamentalsStep(Step):
    name = "fundamentals"
    is_critical = False

    def __init__(self, concurrency: int = 10, attempts: int = 3) -> None:
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    snaps = await _retry(
                        lambda: list(ctx.sources.fundamentals.fetch(ticker)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.upsert_fundamentals(ticker, snaps)
                    return ticker, None
                except Exception as e:
                    logger.warning("fundamentals: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        return StepResult(ok_count=len(results) - len(failures), per_ticker_failures=failures)
