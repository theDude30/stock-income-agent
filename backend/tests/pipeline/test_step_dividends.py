import os
import subprocess
import sys
from datetime import UTC, date, datetime

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
async def test_dividends_step_upserts_and_idempotent(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.dividends import DividendsStep
    from app.sources.base import DividendEvent, Sources, StockMeta
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", None, None)], today=date(2026, 6, 1))
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource(
            {"KO": [DividendEvent(date(2026, 1, 15), date(2026, 2, 1), 0.46)]}
        ),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    step = DividendsStep(concurrency=2, attempts=1)
    result1 = await step.run(ctx)
    await session.commit()
    # KO must be among successes; other carry-over tickers (from earlier tests) get [] from the fake,
    # which is a successful no-op.
    assert "KO" not in result1.per_ticker_failures
    assert await repo.last_dividend_ex_date("KO") == date(2026, 1, 15)

    # Re-run is idempotent
    result2 = await step.run(ctx)
    await session.commit()
    assert "KO" not in result2.per_ticker_failures
    assert await repo.last_dividend_ex_date("KO") == date(2026, 1, 15)


@pytest.mark.asyncio(loop_scope="session")
async def test_dividends_step_isolates_failures(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.dividends import DividendsStep
    from app.sources.base import DividendEvent, Sources, StockMeta
    from app.sources.fakes import (
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    class FlakyDividendSource:
        def fetch(self, ticker, since):
            if ticker == "X":
                raise RuntimeError("nope")
            if ticker == "KO":
                return [DividendEvent(date(2026, 1, 1), None, 0.5)]
            # carry-over from prior tests
            return []

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("KO", "Coca-Cola", None, None), StockMeta("X", "X", None, None)],
        today=date(2026, 6, 1),
    )
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=FlakyDividendSource(),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await DividendsStep(concurrency=2, attempts=1).run(ctx)
    await session.commit()
    assert "X" in result.per_ticker_failures
    assert "nope" in result.per_ticker_failures["X"]
    assert "KO" not in result.per_ticker_failures
