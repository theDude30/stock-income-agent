import asyncio
import logging
from datetime import timedelta

from app.analysis.learning import accept_lesson, survives_contradiction
from app.llm.prompts import LEARNER_PROMPT_VERSION, LEARNER_SYSTEM, build_learner_prompt
from app.llm.schemas import LearnerOutput
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

LEARNER_LOOKBACK_DAYS = 7


class LearnerStep(Step):
    name = "learner"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        if ctx.llm is None:
            logger.warning("learner: no LLM client configured; skipping")
            return StepResult(ok_count=0)

        repo = ctx.repo
        now = ctx.now()
        since = (now - timedelta(days=LEARNER_LOOKBACK_DAYS)).date()

        feedback = await repo.feedback_since(since)
        income = await repo.list_income_events(from_=since, to=now.date())
        rejections = await repo.rejected_recs_since(since)
        held = await repo.held_tickers()

        safety_deltas = []
        for ticker in held:
            delta = await repo.safety_score_delta(ticker)
            if delta is not None:
                safety_deltas.append({"ticker": ticker, "current": delta[0], "previous": delta[1]})

        active = await repo.list_lessons(active=True)
        active_patterns = [lesson.pattern for lesson in active]
        active_by_id = {lesson.id: lesson for lesson in active}

        prompt = build_learner_prompt(
            active_lessons=active_patterns,
            feedback=[{"ticker": f.recommendation_id, "outcome": f.outcome,
                       "total_return_pct": str(f.total_return_pct),
                       "exit_reason": f.exit_reason} for f in feedback],
            income_events=[{"ticker": ie.ticker, "type": ie.type,
                            "amount": str(ie.amount)} for ie in income],
            safety_deltas=safety_deltas,
            rejections=[{"ticker": r.ticker, "type": r.type} for r in rejections],
        )

        output, usage = await asyncio.to_thread(
            ctx.llm.complete_structured,
            system=LEARNER_SYSTEM, prompt=prompt, schema=LearnerOutput,
            prompt_version=LEARNER_PROMPT_VERSION, key="learner",
        )
        await repo.add_llm_usage(ctx.run_id, tokens=usage.input_tokens + usage.output_tokens,
                                 cost=usage.cost_usd)

        # LLM-proposed retirements first
        for retirement in output.retirements:
            await repo.retire_lesson(retirement.lesson_id, retirement.reason, now)

        adopted = 0
        for proposal in output.new_lessons:
            if not accept_lesson(pattern=proposal.pattern, sample_size=proposal.sample_size,
                                 active_patterns=active_patterns):
                continue
            if proposal.contradicts_lesson_id is not None:
                target = active_by_id.get(proposal.contradicts_lesson_id)
                if target is None or target.effective_until is not None:
                    continue
                if not survives_contradiction(proposal.sample_size, target.sample_size):
                    continue
                await repo.retire_lesson(target.id, "superseded by larger-sample lesson", now)
            await repo.insert_lesson(proposal.pattern, proposal.evidence_recommendation_ids,
                                     proposal.sample_size, now)
            active_patterns.append(proposal.pattern)  # catch in-batch duplicates
            adopted += 1

        logger.info("learner: adopted %d lessons, %d retirements proposed",
                    adopted, len(output.retirements))
        return StepResult(ok_count=adopted)
