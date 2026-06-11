import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.pipeline.repo import PipelineRepo


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
async def test_lessons_feedback_settings_endpoints(session, monkeypatch, pg_container):
    # Point create_app()/get_session_factory() at the testcontainer (matches test_portfolio_api.py)
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    now = datetime(2026, 6, 9, 17, 30, tzinfo=UTC)
    lid = await repo.insert_lesson("API lesson visible while active and falsifiable", [1], 6, now)
    ignored_id = await repo.insert_lesson("Ignored lesson should not appear when active only", [2], 6, now)
    await repo.set_lesson_ignored(ignored_id, True)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # active only (default)
        r = await client.get("/lessons")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert lid in ids and ignored_id not in ids

        # include all
        r = await client.get("/lessons?active=false")
        ids = {row["id"] for row in r.json()}
        assert {lid, ignored_id} <= ids

        # ignore toggle
        r = await client.post(f"/lessons/{lid}/ignore", json={"ignored": True})
        assert r.status_code == 200 and r.json()["user_ignored"] is True
        r = await client.post("/lessons/999999/ignore", json={"ignored": True})
        assert r.status_code == 404

        # feedback (empty range is fine — shape check)
        r = await client.get("/feedback")
        assert r.status_code == 200 and isinstance(r.json(), list)

        # settings snapshot
        r = await client.get("/settings")
        body = r.json()
        assert body["approval_modes"]["add_position"] == "manual"
        assert body["auto_execution_enabled"] is False
        assert "smtp_configured" in body["notifications"]
        assert "llm_cost_mtd" in body
