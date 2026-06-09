import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.executor import ExecutorStep
from app.sources.base import Sources, StockMeta


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
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now)


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_add_position(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    from app.models.stocks import Price
    from datetime import date
    session.add(Price(ticker="KO", date=_today, open=Decimal("60"), high=Decimal("61"),
                      low=Decimal("59"), close=Decimal("60.50"), adj_close=Decimal("60.50"), volume=1000000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 5}, reasoning="r", signals_snapshot={},
        model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    positions = await repo.list_open_positions(ticker="KO")
    assert len(positions) == 1
    assert positions[0].shares == Decimal("5")
    rec = await repo.get_recommendation(rec_id)
    assert rec.status == "executed"

    # idempotency: re-run does not open a second position
    result2 = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()
    assert len(await repo.list_open_positions(ticker="KO")) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_sell_covered_call(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="JNJ", confidence="high",
        payload={"strike": "155", "expiration_date": "2026-07-18", "expected_premium": "1.50"},
        reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    calls = await repo.list_open_positions(ticker="JNJ", kind="short_call")
    assert len(calls) == 1 and calls[0].strike == Decimal("155")
    events = await repo.list_income_events()
    assert any(e.ticker == "JNJ" and e.type == "call_premium" for e in events)
    ko_event = next(e for e in events if e.ticker == "JNJ" and e.type == "call_premium")
    assert ko_event.amount == Decimal("150")  # 1.50 premium * 100 shares per contract


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_sell_position(session):
    from datetime import date
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="PG", date=_today, open=Decimal("170"), high=Decimal("172"),
                      low=Decimal("169"), close=Decimal("171"), adj_close=Decimal("171"), volume=500000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    add_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=add_rec_id, ticker="PG", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)

    sell_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_position", ticker="PG", confidence="high",
        payload={"position_id": pos_id}, reasoning="deteriorating", signals_snapshot={},
        model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(sell_rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    pos = await repo.get_position(pos_id)
    assert pos.status == "closed"
    rec = await repo.get_recommendation(sell_rec_id)
    assert rec.status == "executed"
    from app.models.portfolio import Feedback
    from sqlalchemy import select
    fb_rows = (await session.execute(select(Feedback).where(Feedback.position_id == pos_id))).scalars().all()
    assert len(fb_rows) == 1
    fb = fb_rows[0]
    assert fb.outcome in ("win", "loss", "breakeven")
    assert fb.exit_reason == "recommendation"
