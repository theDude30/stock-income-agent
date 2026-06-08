import asyncio
import logging

from app.llm.prompts import SAFETY_PROMPT_VERSION, SAFETY_SYSTEM, build_safety_prompt
from app.llm.schemas import SafetyAssessment
from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.screener import SCREENER_FINALIST_COUNT

logger = logging.getLogger(__name__)


class SafetyStep(Step):
    name = "safety"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        finalists = await ctx.repo.top_screened_tickers(ctx.run_id, limit=SCREENER_FINALIST_COUNT)
        if not finalists:
            return StepResult(ok_count=0)

        failures: dict[str, str] = {}
        ok = 0
        for ticker in finalists:
            try:
                screening = next(
                    (s for s in await ctx.repo.get_screenings(ctx.run_id) if s.ticker == ticker), None)
                signals = screening.signals if screening else {}
                prompt = build_safety_prompt(
                    ticker=ticker, metrics=signals, recent_dividends=[], recent_news=[],
                    active_lessons=[],  # empty until Sub-project 5
                )
                assessment, usage = await asyncio.to_thread(
                    ctx.llm.complete_structured,
                    system=SAFETY_SYSTEM, prompt=prompt, schema=SafetyAssessment,
                    prompt_version=SAFETY_PROMPT_VERSION, key=ticker,
                )
                await ctx.repo.insert_safety_score(
                    ticker=ticker, score=assessment.score,
                    payout_ratio=signals.get("payout_ratio"),
                    fcf_coverage=signals.get("fcf_coverage"),
                    debt_to_equity=signals.get("debt_to_equity"),
                    consecutive_years_paid=signals.get("consecutive_years_paid"),
                    concerns=assessment.concerns, reasoning=assessment.reasoning,
                    model=ctx.llm.model if hasattr(ctx.llm, "model") else "fake",
                    prompt_version=SAFETY_PROMPT_VERSION, now=ctx.now(),
                )
                await ctx.repo.add_llm_usage(
                    ctx.run_id, tokens=usage.input_tokens + usage.output_tokens, cost=usage.cost_usd)
                ok += 1
            except Exception as e:
                logger.warning("safety: %s skipped: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
