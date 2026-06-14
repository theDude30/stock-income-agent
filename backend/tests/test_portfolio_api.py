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


@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_live_marks_to_market(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 11, 17, 15, tzinfo=UTC)
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PEP", "PepsiCo", "S", "B")], today=_now.date())
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PEP", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(
        rec_id=rec_id, ticker="PEP", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)
    await session.commit()

    from app.api import portfolio as portfolio_api
    from app.market.price_cache import PriceCache

    portfolio_api._price_cache_override = PriceCache(fetch=lambda t: Decimal("165"))
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/live")
            assert r.status_code == 200
            body = r.json()
            assert "as_of" in body
            pep = next(p for p in body["positions"] if p["ticker"] == "PEP")
            assert pep["live_price"] == 165.0
            assert pep["live_pnl"] == 50.0          # (165 - 160) * 10
            assert pep["live_pnl_pct"] == pytest.approx(50.0 / 1600.0)
            assert pep["stale"] is False
    finally:
        portfolio_api._price_cache_override = None


@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_live_falls_back_to_db_close_when_fetch_fails(
    session, monkeypatch, pg_container
):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    # PEP position exists from the previous test (shares 10 @ 160, committed).
    # Give it a DB close so the stale fallback has something to return.
    await session.execute(
        pg_insert(Price).values(
            ticker="PEP", date=date(2026, 6, 10), open=Decimal("162"), high=Decimal("163"),
            low=Decimal("161"), close=Decimal("162"), adj_close=Decimal("162"), volume=500,
        ).on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={"close": Decimal("162"), "adj_close": Decimal("162")},
        )
    )
    await session.commit()

    from app.api import portfolio as portfolio_api
    from app.market.price_cache import PriceCache

    def _boom(ticker: str) -> Decimal:
        raise LookupError("yfinance down")

    portfolio_api._price_cache_override = PriceCache(fetch=_boom)
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/live")
            assert r.status_code == 200
            pep = next(p for p in r.json()["positions"] if p["ticker"] == "PEP")
            assert pep["stale"] is True
            assert pep["live_price"] == 162.0
            assert pep["live_pnl"] == 20.0          # (162 - 160) * 10
    finally:
        portfolio_api._price_cache_override = None


@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_performance_includes_spy_and_treasury(
    session, monkeypatch, pg_container
):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    from app.api import pipeline as pipeline_api
    from app.sources.base import PriceBar, Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    spy_bars = [
        PriceBar(date=date(2026, 1, 2), open=100.0, high=100.0, low=100.0,
                 close=100.0, adj_close=100.0, volume=1),
        PriceBar(date=date(2026, 6, 10), open=105.0, high=105.0, low=105.0,
                 close=105.0, adj_close=105.0, volume=1),
    ]
    pipeline_api._sources_override = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({"SPY": spy_bars}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/performance")
            assert r.status_code == 200
            perf = r.json()
            assert "note" not in perf  # SP4 placeholder removed
            assert "ytd_income" in perf
            assert "cost_basis" in perf
            assert "ytd_capital_pnl" in perf
            assert "ytd_total_return_pct" in perf
            assert perf["spy_total_return_pct"] == pytest.approx(0.05)  # 100 → 105
            assert perf["treasury_1m_yield_pct"] == 4.2
            assert 0 < perf["treasury_ytd_return_pct"] < 0.042  # pro-rated YTD fraction
    finally:
        pipeline_api._sources_override = None
