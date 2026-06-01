import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext


def _make_sources():
    # Imported lazily so unit tests don't have to import yfinance.
    from app.sources.base import Sources
    from app.sources.wikipedia_source import WikipediaSP500Source
    from app.sources.yahoo_rss_source import YahooRssNewsSource
    from app.sources.yfinance_source import (
        YFinanceDividendSource,
        YFinanceOptionsSource,
        YFinancePriceSource,
    )
    return Sources(
        universe=WikipediaSP500Source(),
        prices=YFinancePriceSource(),
        dividends=YFinanceDividendSource(),
        options=YFinanceOptionsSource(),
        news=YahooRssNewsSource(),
    )


async def _run(step_filter: str | None) -> int:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        steps = default_steps()
        if step_filter is not None:
            steps = [s for s in steps if s.name == step_filter]
            if not steps:
                print(f"unknown step: {step_filter}", file=sys.stderr)
                return 2
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=0, now=lambda: datetime.now(tz=UTC))
        summary = await run_pipeline(ctx, steps=steps)
        await session.commit()
        print(f"run_id={summary.run_id} status={summary.status} steps={summary.steps_completed}")
        if summary.errors:
            print(f"errors: {summary.errors}")
        return 0 if summary.status != "failed" else 1


async def _backfill() -> int:
    """Force prices + dividends to fetch 5 years of history.

    Same as run, just runs only the prices and dividends steps. Their _since logic
    already does the right thing when DB is empty.
    """
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from app.pipeline.steps import DividendsStep, PricesStep, UniverseStep

        steps = [UniverseStep(), PricesStep(), DividendsStep()]
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=0, now=lambda: datetime.now(tz=UTC))
        summary = await run_pipeline(ctx, steps=steps)
        await session.commit()
        print(f"backfill complete: run_id={summary.run_id} status={summary.status}")
        return 0 if summary.status != "failed" else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="app.pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run the full pipeline (or one step).")
    run_p.add_argument("--step", default=None, help="Run only this step.")

    sub.add_parser("backfill", help="Backfill 5y of prices + dividends.")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        return asyncio.run(_run(args.step))
    if args.cmd == "backfill":
        return asyncio.run(_backfill())
    parser.print_help()
    return 2
