import pytest
from sqlalchemy import text


@pytest.mark.asyncio(loop_scope="session")
async def test_engine_can_execute_select_one(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_app_db_module_provides_get_session(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.db import get_engine, get_session_factory

    eng = get_engine()
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await eng.dispose()
