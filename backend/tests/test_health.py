import sys

import pytest
from httpx import ASGITransport, AsyncClient


def _fresh_app():
    """Re-import app modules so lru_cache'd engine/session_factory rebind to current env."""
    for mod in ("app.main", "app.api.health", "app.db", "app.config"):
        sys.modules.pop(mod, None)
    from app.main import create_app

    return create_app()


@pytest.mark.asyncio(loop_scope="session")
async def test_health_returns_200_and_status_ok(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    app = _fresh_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.asyncio(loop_scope="session")
async def test_health_reports_db_down_when_db_unreachable(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")

    app = _fresh_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["database"] == "down"
