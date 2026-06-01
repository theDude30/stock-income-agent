import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_universe_step_inserts_then_deactivates(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.universe import UniverseStep
    from app.sources.base import Sources, StockMeta
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    sources = Sources(
        universe=InMemoryUniverseSource(
            [
                StockMeta("AAPL", "Apple", "Tech", "Hardware"),
                StockMeta("MSFT", "Microsoft", "Tech", "Software"),
            ]
        ),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(
        repo=repo,
        sources=sources,
        run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )

    result = await UniverseStep().run(ctx)
    await session.commit()
    assert result.ok_count == 2

    # Re-run with shrunk universe → MSFT deactivated.
    sources.universe = InMemoryUniverseSource([StockMeta("AAPL", "Apple", "Tech", "Hardware")])
    result = await UniverseStep().run(ctx)
    await session.commit()
    assert result.ok_count == 1

    active = await repo.list_active_tickers()
    assert "AAPL" in active
    assert "MSFT" not in active


def test_universe_should_run_first_weekday_of_month():
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.universe import UniverseStep

    step = UniverseStep()
    # 2026-06-01 is a Monday → first weekday of the month → run
    ctx_run = StepContext(
        repo=None, sources=None, run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )
    assert step.should_run(ctx_run) is True

    # 2026-06-15 (third Monday) → skip
    ctx_skip = StepContext(
        repo=None, sources=None, run_id=0,
        now=lambda: datetime(2026, 6, 15, 21, 15, tzinfo=UTC),
    )
    assert step.should_run(ctx_skip) is False
