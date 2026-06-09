import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

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
async def test_trades_and_positions_api(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
    _today = _now.date()

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("VZ", "Verizon", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="VZ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="VZ", kind="stock",
        shares=Decimal("20"), avg_entry_price=Decimal("40"),
        strike=None, expiration_date=None, now=_now)
    trade_id = await repo.insert_trade(
        position_id=pos_id, ticker="VZ", side="buy",
        shares_or_contracts=Decimal("20"), price=Decimal("40"),
        reason="recommendation", now=_now)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/trades")
        assert r.status_code == 200
        assert any(t["id"] == trade_id for t in r.json())

        r = await client.get("/positions?status=open")
        assert r.status_code == 200
        assert any(p["id"] == pos_id for p in r.json())

        r = await client.get(f"/positions/{pos_id}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["ticker"] == "VZ"
        assert "trades" in detail
        assert any(t["id"] == trade_id for t in detail["trades"])

        r = await client.get("/positions/99999")
        assert r.status_code == 404
