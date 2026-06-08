import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.fundamentals import FundamentalsStep
from app.sources.base import FundamentalsSnapshot, Sources
from app.sources.fakes import InMemoryFundamentalsSource


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


def _ctx(session, fundamentals):
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=fundamentals)
    return StepContext(repo=PipelineRepo(session), sources=sources, run_id=1,
                       now=_now, llm=FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0)))


@pytest.mark.asyncio(loop_scope="session")
async def test_fundamentals_step_upserts(session):
    repo = PipelineRepo(session)
    from app.sources.base import StockMeta
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    await session.commit()

    src = InMemoryFundamentalsSource({"KO": [FundamentalsSnapshot(
        "2026Q1", 100.0, 2.0, 30.0, 20.0, 50.0, 80.0, 10.0)]})
    result = await FundamentalsStep().run(_ctx(session, src))
    await session.commit()

    assert result.ok_count == 1
    assert await repo.latest_fundamentals("KO") is not None
