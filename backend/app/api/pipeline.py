import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext
from app.sources.base import Sources
from app.sources.wikipedia_source import WikipediaSP500Source
from app.sources.yahoo_rss_source import YahooRssNewsSource
from app.sources.yfinance_source import (
    YFinanceDividendSource,
    YFinanceOptionsSource,
    YFinancePriceSource,
)

router = APIRouter(prefix="/pipeline")
logger = logging.getLogger(__name__)

# Test seam: set to a Sources instance to override production wiring.
_sources_override: Sources | None = None


def _make_sources() -> Sources:
    if _sources_override is not None:
        return _sources_override
    return Sources(
        universe=WikipediaSP500Source(),
        prices=YFinancePriceSource(),
        dividends=YFinanceDividendSource(),
        options=YFinanceOptionsSource(),
        news=YahooRssNewsSource(),
    )


@router.get("/runs")
async def list_runs(limit: int = 30) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        runs = await repo.recent_runs(limit=limit)
        return [_run_to_dict(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        run = await repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _run_to_dict(run, full=True)


@router.post("/run", status_code=202)
async def trigger_run(
    background_tasks: BackgroundTasks,
    step: str | None = Query(default=None),
) -> dict:
    # Resolve step list first so unknown-step returns 400 synchronously.
    steps = default_steps()
    if step is not None:
        steps = [s for s in steps if s.name == step]
        if not steps:
            raise HTTPException(status_code=400, detail=f"unknown step: {step}")

    # Start the run synchronously so the caller has a stable run_id before
    # the background task fires.
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        run_id = await repo.start_run(now=datetime.now(tz=UTC))
        await session.commit()

    background_tasks.add_task(
        _run_in_background, run_id=run_id, step_names=[s.name for s in steps]
    )
    return {"run_id": run_id}


async def _run_in_background(run_id: int, step_names: list[str]) -> None:
    name_to_step = {s.name: s for s in default_steps()}
    steps = [name_to_step[n] for n in step_names if n in name_to_step]

    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=run_id)
        try:
            await run_pipeline(ctx, steps=steps, existing_run_id=run_id)
            await session.commit()
        except Exception:
            logger.exception("background pipeline failed")
            await session.rollback()


def _run_to_dict(run, full: bool = False) -> dict:
    out = {
        "id": run.id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "steps_completed": list(run.steps_completed or []),
        "error_count": len(run.errors or {}),
    }
    if full:
        out["errors"] = run.errors or {}
    return out
