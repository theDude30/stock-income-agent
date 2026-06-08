import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.recommender import RecommenderStep
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


@pytest.mark.asyncio(loop_scope="session")
async def test_recommender_emits_add_position_for_safe_unheld(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    run_id = await repo.start_run(now=_now())
    await repo.insert_screening(run_id, "KO", 85.0, {"ttm_yield": 0.03}, True, _now())
    await repo.insert_safety_score("KO", 80, 0.5, 3.0, 0.4, 30, [], "solid",
                                   "claude-sonnet-4-6", "safety-v1", _now())
    await session.commit()

    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now)
    result = await RecommenderStep().run(ctx)
    await session.commit()

    assert result.ok_count >= 1
    recs = await repo.list_recommendations(status="pending", type_="add_position")
    assert any(r.ticker == "KO" for r in recs)
