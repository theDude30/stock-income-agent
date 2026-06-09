import os
import subprocess
import sys

import pytest
from sqlalchemy import text


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
async def test_portfolio_tables_exist(session):
    for table in ("positions", "trades", "income_events", "feedback"):
        result = await session.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
            {"t": table},
        )
        assert result.scalar() == 1, f"table {table!r} not found"
