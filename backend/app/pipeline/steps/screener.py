import logging

from app.analysis.screener import (
    ScreenerSignals,
    compute_debt_to_equity,
    compute_fcf_coverage,
    compute_payout_ratio,
    compute_quality_score,
    compute_ttm_yield,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

SCREENER_FINALIST_COUNT = 30
PASS_THRESHOLD = 50.0


class ScreenerStep(Step):
    name = "screener"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        today = ctx.now().date()
        failures: dict[str, str] = {}
        ok = 0
        for ticker in tickers:
            try:
                price = await ctx.repo.latest_close(ticker)
                ttm = await ctx.repo.ttm_dividends(ticker, today)
                years = await ctx.repo.consecutive_years_paid(ticker)
                f = await ctx.repo.latest_fundamentals(ticker)

                def fv(x):
                    return float(x) if x is not None else None

                signals = ScreenerSignals(
                    ttm_yield=compute_ttm_yield(ttm, price),
                    payout_ratio=compute_payout_ratio(
                        fv(f.dividends_paid) if f else None, fv(f.net_income) if f else None),
                    fcf_coverage=compute_fcf_coverage(
                        fv(f.fcf) if f else None, fv(f.dividends_paid) if f else None),
                    debt_to_equity=compute_debt_to_equity(
                        fv(f.total_debt) if f else None, fv(f.total_equity) if f else None),
                    consecutive_years_paid=years,
                    earnings_growth_5y=None,  # requires 5y of fundamentals; filled in later
                )
                score = compute_quality_score(signals)
                await ctx.repo.insert_screening(
                    run_id=ctx.run_id, ticker=ticker, score=score,
                    signals={
                        "ttm_yield": signals.ttm_yield,
                        "payout_ratio": signals.payout_ratio,
                        "fcf_coverage": signals.fcf_coverage,
                        "debt_to_equity": signals.debt_to_equity,
                        "consecutive_years_paid": signals.consecutive_years_paid,
                    },
                    passed=score >= PASS_THRESHOLD, now=ctx.now(),
                )
                ok += 1
            except Exception as e:
                logger.warning("screener: %s failed: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
