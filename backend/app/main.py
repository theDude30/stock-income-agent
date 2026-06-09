import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.pipeline import _make_llm, _make_sources
from app.api.pipeline import router as pipeline_router
from app.api.portfolio import router as portfolio_router
from app.api.recommendations import router as recommendations_router
from app.api.stocks import router as stocks_router
from app.api.trades import router as trades_router
from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.scheduler import PipelineScheduler
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext

logger = logging.getLogger(__name__)


async def _scheduled_pipeline_job() -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        ctx = StepContext(
            repo=repo,
            sources=_make_sources(),
            run_id=0,
            now=lambda: datetime.now(tz=UTC),
            llm=_make_llm(),
        )
        try:
            await run_pipeline(ctx, steps=default_steps())
            await session.commit()
        except Exception:
            logger.exception("scheduled pipeline failed")
            await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = PipelineScheduler(job_callable=_scheduled_pipeline_job)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Income Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(pipeline_router)
    app.include_router(recommendations_router)
    app.include_router(stocks_router)
    app.include_router(portfolio_router)
    app.include_router(trades_router)
    return app


app = create_app()
