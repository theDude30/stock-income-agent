import logging

from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

SAFETY_ADD_THRESHOLD = 70  # min safety score to recommend a new position


class RecommenderStep(Step):
    name = "recommender"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        held = set(await ctx.repo.held_tickers())
        finalists = await ctx.repo.top_screened_tickers(ctx.run_id, limit=30)
        screenings = {s.ticker: s for s in await ctx.repo.get_screenings(ctx.run_id)}

        ok = 0
        for ticker in finalists:
            if ticker in held:
                continue
            safety = await ctx.repo.latest_safety_score(ticker)
            if safety is None or safety.score < SAFETY_ADD_THRESHOLD:
                continue
            screening = screenings.get(ticker)
            confidence = "high" if safety.score >= 85 else "med"
            await ctx.repo.insert_recommendation(
                run_id=ctx.run_id, type="add_position", ticker=ticker, confidence=confidence,
                payload={"target_shares": None, "target_price": "market",
                         "expected_yield": (screening.signals.get("ttm_yield") if screening else None)},
                reasoning=safety.llm_reasoning,
                signals_snapshot={
                    "quality_score": float(screening.dividend_quality_score) if screening else None,
                    "safety_score": safety.score,
                    "signals": screening.signals if screening else {},
                },
                model=safety.llm_model, prompt_version=safety.llm_prompt_version, now=ctx.now(),
            )
            ok += 1
        return StepResult(ok_count=ok)
