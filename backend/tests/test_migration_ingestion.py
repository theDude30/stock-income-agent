import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio(loop_scope="session")
async def test_migration_creates_all_ingestion_tables(monkeypatch, pg_container, engine):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env={**os.environ},
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, f"alembic failed: {result.stderr}"

    expected = {
        "stocks",
        "prices",
        "dividend_history",
        "options_chains",
        "news_items",
        "pipeline_runs",
        "alembic_version",
    }
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert expected.issubset(set(tables)), f"missing: {expected - set(tables)}"
