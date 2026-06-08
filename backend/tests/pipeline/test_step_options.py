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
async def test_options_step_limits_to_top_watchlist(session, monkeypatch, pg_container):
    """Verify watchlist comes from top_tickers_by_ttm_yield and respects the limit.

    Seeds 3 tickers with different yields, sets watchlist_size=1, verifies only
    the top-yield ticker has options inserted.
    """
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from sqlalchemy import select

    from app.models.options import OptionsChainRow as OptionsRowORM
    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.options import OptionsStep
    from app.sources.base import (
        DividendEvent,
        OptionsChainRow,
        PriceBar,
        Sources,
        StockMeta,
    )
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    # Force the TTM-yield fallback path (this test targets `top_tickers_by_ttm_yield`
    # specifically). Without this, a `Screening` row left behind by another test in
    # the shared session-scoped DB would make `latest_screening_run_id` non-null and
    # redirect the watchlist through `top_screened_tickers` instead.
    async def _no_screening_run(self):
        return None

    monkeypatch.setattr(PipelineRepo, "latest_screening_run_id", _no_screening_run)
    # Use unique tickers for this test that won't collide with carryover state.
    await repo.upsert_stocks(
        [
            StockMeta("OPTHI", "High Yield Co", None, None),
            StockMeta("OPTLO", "Low Yield Co", None, None),
            StockMeta("OPTNO", "No Div Co", None, None),
        ],
        today=date(2026, 6, 1),
    )
    for t, close in [("OPTHI", 100.0), ("OPTLO", 100.0), ("OPTNO", 100.0)]:
        await repo.upsert_prices(t, [PriceBar(date(2026, 6, 1), close, close, close, close, close, 1000)])
    # Use a recent ex_date (within last 12 months of today=2026-06-01) so it enters TTM window.
    await repo.upsert_dividends("OPTHI", [DividendEvent(date(2026, 5, 1), None, 10.0)])
    await repo.upsert_dividends("OPTLO", [DividendEvent(date(2026, 5, 1), None, 0.10)])
    await session.commit()

    chains = {
        "OPTHI": [
            OptionsChainRow(date(2026, 7, 17), 110.0, "call", 1.0, 1.1, 1.05, 0.30, 50, 200),
        ],
        "OPTLO": [
            OptionsChainRow(date(2026, 7, 17), 110.0, "call", 1.0, 1.1, 1.05, 0.30, 50, 200),
        ],
        "OPTNO": [
            OptionsChainRow(date(2026, 7, 17), 110.0, "call", 1.0, 1.1, 1.05, 0.30, 50, 200),
        ],
    }
    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource(chains),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await OptionsStep(watchlist_size=1, concurrency=2, attempts=1).run(ctx)
    await session.commit()
    assert result.ok_count == 1

    # Verify exactly OPTHI was inserted as an options snapshot (not OPTLO, not OPTNO).
    rows = await session.execute(
        select(OptionsRowORM.ticker).distinct().where(OptionsRowORM.ticker.in_(["OPTHI", "OPTLO", "OPTNO"]))
    )
    inserted = {r[0] for r in rows.all()}
    assert inserted == {"OPTHI"}
