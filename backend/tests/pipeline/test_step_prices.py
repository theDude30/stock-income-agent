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


async def _seed_stocks(repo, tickers):
    from app.sources.base import StockMeta
    await repo.upsert_stocks([StockMeta(t, t, None, None) for t in tickers], today=date(2026, 6, 1))


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_happy_path(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import PriceBar, Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    await _seed_stocks(repo, ["AAPL", "MSFT"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource(
            {
                "AAPL": [PriceBar(date(2026, 6, 1), 100, 101, 99, 100.5, 100.5, 1000)],
                "MSFT": [PriceBar(date(2026, 6, 1), 200, 201, 199, 200.5, 200.5, 2000)],
            }
        ),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await PricesStep(concurrency=2).run(ctx)
    await session.commit()
    # Note: there may be more than 2 tickers active from previous tests (e.g. GOOG from repo tests).
    # Verify at least our 2 fakes succeeded and others (which the fake doesn't know about) failed gracefully.
    assert "AAPL" not in result.per_ticker_failures
    assert "MSFT" not in result.per_ticker_failures
    assert await repo.last_price_date("AAPL") == date(2026, 6, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_isolates_per_ticker_failures(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import PriceBar, Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryUniverseSource,
    )

    class FlakyPriceSource:
        def fetch(self, ticker, since):
            if ticker == "MSFT":
                raise RuntimeError("simulated yfinance failure")
            if ticker == "AAPL":
                return [PriceBar(date(2026, 6, 1), 100, 101, 99, 100.5, 100.5, 1000)]
            # Padding tickers (GOOG, AMZN, META, NVDA) return empty bars — valid success.
            return []

    repo = PipelineRepo(session)
    # Seed AAPL + MSFT plus enough padding tickers so that even with MSFT failing,
    # the success rate stays above the 80% critical threshold (5/6 ≈ 83%).
    # FlakyPriceSource returns [] for the padding tickers, which counts as a success.
    await _seed_stocks(repo, ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=FlakyPriceSource(),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await PricesStep(concurrency=2, attempts=1).run(ctx)
    await session.commit()
    # Verify exact isolation: MSFT failed, AAPL succeeded.
    assert "MSFT" in result.per_ticker_failures
    assert "yfinance failure" in result.per_ticker_failures["MSFT"]
    assert "AAPL" not in result.per_ticker_failures


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_fails_when_below_critical_threshold(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext, StepFailure
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryUniverseSource,
    )

    class AlwaysFailPriceSource:
        def fetch(self, ticker, since):
            raise RuntimeError("everything is broken")

    repo = PipelineRepo(session)
    await _seed_stocks(repo, ["AAPL", "MSFT", "GOOG", "AMZN", "META"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=AlwaysFailPriceSource(),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    with pytest.raises(StepFailure):
        await PricesStep(concurrency=2, attempts=1, critical_success_threshold=0.8).run(ctx)
