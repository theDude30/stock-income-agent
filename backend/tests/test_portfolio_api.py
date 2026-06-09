import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.main import create_app
from app.models.stocks import Price
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
async def test_portfolio_api(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
    _today = _now.date()

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    from app.models.stocks import DividendHistory
    # Upsert price to avoid duplicate-key error when executor tests have already
    # inserted a KO price for the same date in the same shared session/DB.
    await session.execute(
        pg_insert(Price).values(
            ticker="KO", date=_today, open=Decimal("61"), high=Decimal("62"),
            low=Decimal("60"), close=Decimal("61.50"), adj_close=Decimal("61.50"), volume=1000000,
        ).on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={"close": Decimal("61.50"), "adj_close": Decimal("61.50")},
        )
    )
    session.add(DividendHistory(ticker="KO", ex_date=date(2026, 6, 15), pay_date=None,
                                amount_per_share=Decimal("0.485"), frequency="quarterly"))
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("60"),
        strike=None, expiration_date=None, now=_now)
    await repo.insert_income_event(
        ticker="KO", type_="dividend", amount=Decimal("4.85"),
        event_date=date(2026, 3, 15),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/portfolio/holdings")
        assert r.status_code == 200
        holdings = r.json()
        assert any(h["ticker"] == "KO" for h in holdings)
        ko = next(h for h in holdings if h["ticker"] == "KO")
        assert "price_date" in ko
        assert "unrealized_pnl" in ko

        r = await client.get("/portfolio/income")
        assert r.status_code == 200
        assert any(e["ticker"] == "KO" for e in r.json())

        r = await client.get("/portfolio/income/calendar?days=30")
        assert r.status_code == 200
        cal = r.json()
        assert "upcoming_dividends" in cal
        assert "expiring_calls" in cal
        assert isinstance(cal["upcoming_dividends"], list)
        assert isinstance(cal["expiring_calls"], list)

        r = await client.get("/portfolio/performance")
        assert r.status_code == 200
        perf = r.json()
        assert "ytd_income" in perf
        assert "cost_basis" in perf
