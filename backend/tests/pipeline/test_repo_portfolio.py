import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

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
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_position_lifecycle(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 10}, reasoning="test", signals_snapshot={},
        model="m", prompt_version="v", now=_now)

    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("60.00"),
        strike=None, expiration_date=None, now=_now)
    assert pos_id > 0

    positions = await repo.list_open_positions(ticker="KO")
    assert len(positions) == 1 and positions[0].id == pos_id

    positions_by_kind = await repo.list_open_positions(kind="stock")
    assert any(p.id == pos_id for p in positions_by_kind)

    pos = await repo.get_position(pos_id)
    assert pos is not None and pos.status == "open"

    await repo.close_position(pos_id, "closed", _now)
    pos = await repo.get_position(pos_id)
    assert pos.status == "closed"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_trade_insert_and_list(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="JNJ", kind="stock",
        shares=Decimal("5"), avg_entry_price=Decimal("150"),
        strike=None, expiration_date=None, now=_now)

    trade_id = await repo.insert_trade(
        position_id=pos_id, ticker="JNJ", side="buy",
        shares_or_contracts=Decimal("5"), price=Decimal("150"),
        reason="recommendation", now=_now)
    assert trade_id > 0

    trades = await repo.list_trades()
    assert any(t.id == trade_id for t in trades)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_income_event_dedup(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="PG", kind="stock",
        shares=Decimal("20"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)

    ev_id = await repo.insert_income_event(
        ticker="PG", type_="dividend", amount=Decimal("48.20"),
        event_date=date(2026, 6, 1),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    assert ev_id is not None

    # duplicate → None (ON CONFLICT DO NOTHING)
    dup_id = await repo.insert_income_event(
        ticker="PG", type_="dividend", amount=Decimal("48.20"),
        event_date=date(2026, 6, 1),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    assert dup_id is None

    events = await repo.list_income_events()
    assert sum(1 for e in events if e.ticker == "PG") == 1
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_feedback_insert(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("MMM", "3M", "I", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="MMM", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="MMM", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("100"),
        strike=None, expiration_date=None, now=_now)

    fb_id = await repo.insert_feedback(
        rec_id=rec_id, position_id=pos_id,
        entry_price=Decimal("100"), exit_price=Decimal("110"),
        capital_pnl=Decimal("100"), dividends_received=Decimal("0"),
        premiums_collected=Decimal("0"), total_return_pct=Decimal("0.10"),
        held_days=30, outcome="win", exit_reason="recommendation", now=_now)
    assert fb_id > 0
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_approved_unexecuted_recs_and_mark_executed(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("VZ", "Verizon", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="VZ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)

    recs = await repo.approved_unexecuted_recs()
    assert any(r.id == rec_id for r in recs)

    await repo.mark_rec_executed(rec_id)
    recs_after = await repo.approved_unexecuted_recs()
    assert not any(r.id == rec_id for r in recs_after)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_open_calls_expiring_on(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("T", "AT&T", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="T", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(
        rec_id=rec_id, ticker="T", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("0.50"),
        strike=Decimal("20"), expiration_date=_today,
        now=_now)

    calls = await repo.open_calls_expiring_on(_today)
    assert any(p.ticker == "T" and p.expiration_date == _today for p in calls)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_dividends_since_excludes_open_date(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("O", "Realty", "RE", "B")], today=_today)
    from app.models.stocks import DividendHistory as DH
    session.add(DH(ticker="O", ex_date=_today, pay_date=None,
                   amount_per_share=Decimal("0.257"), frequency="monthly"))
    await session.flush()

    divs = await repo.dividends_since("O", _today)
    assert divs == []  # ex_date == since_date is excluded (strict >)

    divs2 = await repo.dividends_since("O", date(2026, 6, 8))
    assert len(divs2) == 1
    await session.commit()
