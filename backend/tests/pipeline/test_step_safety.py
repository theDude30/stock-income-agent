import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import SafetyAssessment
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.safety import SafetyStep
from app.sources.base import Sources, StockMeta


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


def _ctx(session, llm):
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=None)
    return StepContext(repo=PipelineRepo(session), sources=sources, run_id=_RUN, now=_now, llm=llm)


_RUN = None


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_writes_scores_and_skips_bad(session):
    global _RUN
    repo = PipelineRepo(session)
    for t in ("KO", "BAD"):
        await repo.upsert_stocks([StockMeta(t, t, "S", "B")], today=_now().date())
    _RUN = await repo.start_run(now=_now())
    await repo.insert_screening(_RUN, "KO", 82.0, {"ttm_yield": 0.03}, True, _now())
    await repo.insert_screening(_RUN, "BAD", 70.0, {"ttm_yield": 0.05}, True, _now())
    await session.commit()

    llm = FakeLLMClient(
        by_key={"KO": SafetyAssessment(score=85, concerns=[], outlook="stable", reasoning="ok")},
        usage=LLMUsage(1000, 200, 0.006), raise_for={"BAD"},
    )
    result = await SafetyStep().run(_ctx(session, llm))
    await session.commit()

    assert result.ok_count == 1
    assert "BAD" in result.per_ticker_failures
    assert (await repo.latest_safety_score("KO")).score == 85
    run = await repo.get_run(_RUN)
    assert run.llm_tokens_used == 1200  # only KO succeeded
