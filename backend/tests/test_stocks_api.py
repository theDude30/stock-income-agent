import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.pipeline.repo import PipelineRepo
from app.sources.base import StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_and_screenings(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=datetime(2026, 6, 8).date())
    run_id = await repo.start_run(now=datetime(2026, 6, 8, tzinfo=UTC))
    await repo.insert_screening(run_id, "PG", 77.0, {"ttm_yield": 0.025}, True, datetime(2026, 6, 8, tzinfo=UTC))
    await repo.insert_safety_score("PG", 88, 0.55, 2.5, 0.5, 60, ["none"], "rock solid",
                                   "claude-sonnet-4-6", "safety-v1", datetime(2026, 6, 8, tzinfo=UTC))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/stocks/PG/safety-score")
        assert r.status_code == 200 and r.json()["score"] == 88

        r = await client.get("/stocks/NOPE/safety-score")
        assert r.status_code == 404

        r = await client.get(f"/screenings?run_id={run_id}")
        assert r.status_code == 200 and any(s["ticker"] == "PG" for s in r.json())
