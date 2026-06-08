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
async def test_list_get_approve_reject(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=datetime(2026, 6, 8).date())
    run_id = await repo.start_run(now=datetime(2026, 6, 8, tzinfo=UTC))
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_price": "market"}, reasoning="solid", signals_snapshot={"safety_score": 80},
        model="claude-sonnet-4-6", prompt_version="safety-v1", now=datetime(2026, 6, 8, tzinfo=UTC))
    rec2 = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="med",
        payload={}, reasoning="ok", signals_snapshot={}, model="m", prompt_version="v",
        now=datetime(2026, 6, 8, tzinfo=UTC))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/recommendations")
        assert r.status_code == 200
        assert any(item["id"] == rec_id for item in r.json())

        r = await client.get(f"/recommendations/{rec_id}")
        assert r.json()["reasoning"] == "solid"

        r = await client.post(f"/recommendations/{rec_id}/approve")
        assert r.status_code == 200 and r.json()["status"] == "approved"

        r = await client.post(f"/recommendations/{rec_id}/approve")
        assert r.status_code == 409  # already decided

        r = await client.post(f"/recommendations/{rec2}/reject", json={"reason": "too pricey"})
        assert r.status_code == 200 and r.json()["status"] == "rejected"
