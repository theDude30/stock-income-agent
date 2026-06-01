import os
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient


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
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        check=True,
    )


def _fresh_app():
    import sys as _sys
    for m in ("app.main", "app.api.health", "app.api.pipeline", "app.db", "app.config"):
        _sys.modules.pop(m, None)
    from app.main import create_app
    return create_app()


@pytest.mark.asyncio(loop_scope="session")
async def test_pipeline_runs_empty_initially(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    app = _fresh_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/pipeline/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_pipeline_run_post_creates_run_row(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    app = _fresh_app()

    # Replace production sources with fakes so the run doesn't actually call yfinance.
    from app.api import pipeline as pipeline_api
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )
    pipeline_api._sources_override = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/pipeline/run")
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        assert run_id > 0

        # Eventually visible in list (BackgroundTask should run quickly with empty sources).
        runs = (await client.get("/pipeline/runs")).json()
        assert any(r["id"] == run_id for r in runs)

    pipeline_api._sources_override = None
