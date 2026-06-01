import asyncio
import logging
from collections.abc import Callable
from datetime import date

from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult

logger = logging.getLogger(__name__)


async def _retry(fn: Callable, attempts: int, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.to_thread(fn)
        except Exception as e:
            last_exc = e
            if attempt == attempts - 1:
                break
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc


class PricesStep(Step):
    name = "prices"
    is_critical = True

    def __init__(
        self,
        concurrency: int = 10,
        attempts: int = 3,
        critical_success_threshold: float = 0.8,
        backfill_years: int = 5,
    ) -> None:
        self.concurrency = concurrency
        self.attempts = attempts
        self.critical_success_threshold = critical_success_threshold
        self.backfill_years = backfill_years

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        sem = asyncio.Semaphore(self.concurrency)
        today = ctx.now().date()

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    last = await ctx.repo.last_price_date(ticker)
                    since = self._since(last, today)
                    bars = await _retry(
                        lambda: list(ctx.sources.prices.fetch(ticker, since)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.upsert_prices(ticker, bars)
                    return ticker, None
                except Exception as e:
                    logger.warning("prices: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        success_rate = ok / len(results)
        if success_rate < self.critical_success_threshold:
            raise StepFailure(
                f"prices step success rate {success_rate:.0%} < threshold "
                f"{self.critical_success_threshold:.0%}"
            )
        return StepResult(ok_count=ok, per_ticker_failures=failures)

    def _since(self, last: date | None, today: date) -> date | None:
        if last is None:
            try:
                return date(today.year - self.backfill_years, today.month, today.day)
            except ValueError:
                # Feb 29 → Feb 28
                return date(today.year - self.backfill_years, today.month, today.day - 1)
        from datetime import timedelta

        return last + timedelta(days=1)
