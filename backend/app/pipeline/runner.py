import logging
from dataclasses import dataclass

from app.pipeline.steps.base import Step, StepContext, StepFailure

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunSummary:
    run_id: int
    status: str  # success | partial | failed
    steps_completed: list[str]
    errors: dict[str, dict]


async def run_pipeline(
    ctx: StepContext,
    steps: list[Step],
    existing_run_id: int | None = None,
) -> PipelineRunSummary:
    if existing_run_id is None:
        run_id = await ctx.repo.start_run(now=ctx.now())
    else:
        run_id = existing_run_id
    ctx.run_id = run_id

    completed: list[str] = []
    errors: dict[str, dict] = {}
    failed_critical = False

    for step in steps:
        if not step.should_run(ctx):
            logger.info("pipeline: skipping step %s (should_run=False)", step.name)
            continue
        try:
            logger.info("pipeline: starting step %s", step.name)
            result = await step.run(ctx)
            completed.append(step.name)
            if result.per_ticker_failures:
                errors[step.name] = {
                    "per_ticker": result.per_ticker_failures,
                    "ok_count": result.ok_count,
                }
            logger.info(
                "pipeline: step %s ok=%d failures=%d",
                step.name,
                result.ok_count,
                len(result.per_ticker_failures),
            )
        except StepFailure as e:
            logger.warning("pipeline: step %s failed: %s", step.name, e)
            errors[step.name] = {"reason": str(e)}
            if step.is_critical:
                failed_critical = True
                break

    if failed_critical:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"

    await ctx.repo.finish_run(run_id, status=status, completed=completed, errors=errors, now=ctx.now())
    return PipelineRunSummary(run_id=run_id, status=status, steps_completed=completed, errors=errors)
