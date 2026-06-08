import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.screener import ScreenerStep
from app.sources.base import (
    DividendEvent,
    FundamentalsSnapshot,
    PriceBar,
    Sources,
    StockMeta,
)


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_screener_writes_rows_and_passes_quality_names(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    await repo.upsert_prices("KO", [PriceBar(date(2026, 6, 5), 60, 61, 59, 60, 60, 1000)])
    await repo.upsert_dividends("KO", [DividendEvent(date(2026, 3, 15), date(2026, 4, 1), 0.46)])
    await repo.upsert_fundamentals("KO", [FundamentalsSnapshot(
        "2026Q1", 100.0, 2.0, 30.0, 20.0, 50.0, 80.0, 10.0)])
    run_id = await repo.start_run(now=_now())
    await session.commit()

    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now)
    result = await ScreenerStep().run(ctx)
    await session.commit()

    assert result.ok_count == 1
    screenings = await repo.get_screenings(run_id)
    assert len(screenings) == 1
    assert "ttm_yield" in screenings[0].signals
