import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.options_recommender import OptionsRecommenderStep
from app.sources.base import Sources


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
async def test_options_recommender_dormant_when_no_options_data(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now())
    await session.commit()
    llm = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0))
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now, llm=llm)

    result = await _run_options_recommender(ctx)
    # With no options data (sources.options is None), ok_count must be 0
    # regardless of how many stock positions are held.
    assert result.ok_count == 0
    # No sell_covered_call recommendations should have been produced by THIS run
    from sqlalchemy import select

    from app.models.recommendation import Recommendation
    run_recs = (await session.execute(
        select(Recommendation).where(
            Recommendation.run_id == run_id,
            Recommendation.type == "sell_covered_call",
        )
    )).scalars().all()
    assert run_recs == []


async def _run_options_recommender(ctx):
    return await OptionsRecommenderStep().run(ctx)
