import asyncio
import logging

from app.analysis.options_scoring import filter_otm_calls, score_call
from app.llm.prompts import OPTIONS_PROMPT_VERSION, OPTIONS_SYSTEM, build_options_prompt
from app.llm.schemas import CallPick
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class OptionsRecommenderStep(Step):
    name = "options_recommender"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        holdings = await ctx.repo.held_tickers()
        if not holdings:
            return StepResult(ok_count=0)

        failures: dict[str, str] = {}
        ok = 0
        for ticker in holdings:
            try:
                price = await ctx.repo.latest_close(ticker)
                rows = list(ctx.sources.options.fetch(ticker)) if ctx.sources.options else []
                candidates = filter_otm_calls(rows, price or 0.0)
                scored = sorted((score_call(c, price or 0.0) for c in candidates),
                                key=lambda s: s.score, reverse=True)[:5]
                if not scored:
                    continue
                payload = [
                    {"strike": s.candidate.strike, "premium": s.candidate.premium,
                     "premium_yield": s.premium_yield, "prob_assignment": s.prob_assignment,
                     "expiration_date": s.candidate.expiration_date}
                    for s in scored
                ]
                pick, usage = await asyncio.to_thread(
                    ctx.llm.complete_structured,
                    system=OPTIONS_SYSTEM,
                    prompt=build_options_prompt(ticker=ticker, price=price or 0.0, candidates=payload),
                    schema=CallPick, prompt_version=OPTIONS_PROMPT_VERSION, key=ticker,
                )
                await ctx.repo.insert_recommendation(
                    run_id=ctx.run_id, type="sell_covered_call", ticker=ticker, confidence="med",
                    payload={"strike": pick.strike, "expiration_date": str(pick.expiration_date),
                             "expected_premium": pick.expected_premium,
                             "prob_assignment": pick.prob_assignment},
                    reasoning=pick.reasoning, signals_snapshot={"candidates": payload},
                    model=getattr(ctx.llm, "model", "fake"),
                    prompt_version=OPTIONS_PROMPT_VERSION, now=ctx.now(),
                )
                await ctx.repo.add_llm_usage(
                    ctx.run_id, tokens=usage.input_tokens + usage.output_tokens, cost=usage.cost_usd)
                ok += 1
            except Exception as e:
                logger.warning("options_recommender: %s skipped: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
