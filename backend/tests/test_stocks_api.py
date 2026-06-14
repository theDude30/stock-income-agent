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


@pytest.mark.asyncio(loop_scope="session")
async def test_stock_detail_prices_dividends(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    from datetime import date
    from decimal import Decimal

    from app.models.stocks import DividendHistory, Price

    _now = datetime(2026, 6, 11, tzinfo=UTC)
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KMB", "Kimberly-Clark", "Staples", "Household")],
                             today=_now.date())
    run_id = await repo.start_run(now=_now)
    await repo.insert_screening(run_id, "KMB", 81.0, {"ttm_yield": 0.034}, True, _now)
    await repo.insert_safety_score("KMB", 79, 0.6, 1.8, 0.7, 52, [], "steady",
                                   "m", "v", _now)
    for d, close in [(date(2026, 6, 9), "130"), (date(2026, 6, 10), "131")]:
        session.add(Price(ticker="KMB", date=d, open=Decimal(close), high=Decimal(close),
                          low=Decimal(close), close=Decimal(close), adj_close=Decimal(close),
                          volume=2000))
    session.add(DividendHistory(ticker="KMB", ex_date=date(2026, 3, 6), pay_date=date(2026, 4, 2),
                                amount_per_share=Decimal("1.22"), frequency="quarterly"))
    session.add(DividendHistory(ticker="KMB", ex_date=date(2026, 6, 5), pay_date=None,
                                amount_per_share=Decimal("1.22"), frequency="quarterly"))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # detail
        r = await client.get("/stocks/KMB")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Kimberly-Clark"
        assert body["latest_screening"]["dividend_quality_score"] == 81.0
        assert body["latest_safety_score"]["score"] == 79

        r = await client.get("/stocks/NOPE")
        assert r.status_code == 404

        # prices, with and without window
        r = await client.get("/stocks/KMB/prices")
        assert r.status_code == 200 and len(r.json()) == 2

        r = await client.get("/stocks/KMB/prices?from=2026-06-10&to=2026-06-10")
        rows = r.json()
        assert len(rows) == 1 and rows[0]["close"] == 131.0

        # dividends, newest first
        r = await client.get("/stocks/KMB/dividends")
        divs = r.json()
        assert [d["ex_date"] for d in divs] == ["2026-06-05", "2026-03-06"]
        assert divs[0]["amount_per_share"] == 1.22
