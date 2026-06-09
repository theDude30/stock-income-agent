import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.income_tracker import IncomeTrackerStep
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


_open_date = datetime(2026, 6, 1, 17, 0, tzinfo=UTC)
_ex_date = date(2026, 6, 5)  # strictly after open date
_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, now=None):
    t = now or _now
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: t)


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_books_dividend(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    session.add(DividendHistory(ticker="KO", ex_date=_ex_date, pay_date=None,
                   amount_per_share=Decimal("0.485"), frequency="quarterly"))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("60"),
        strike=None, expiration_date=None, now=_open_date)
    await session.commit()

    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    events = await repo.list_income_events()
    div_events = [e for e in events if e.ticker == "KO" and e.type == "dividend"]
    assert len(div_events) == 1
    assert div_events[0].amount == Decimal("48.50")  # 0.485 * 100

    # idempotency: run again, no duplicate
    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()
    events2 = await repo.list_income_events()
    assert len([e for e in events2 if e.ticker == "KO" and e.type == "dividend"]) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_otm_call_expiry(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="JNJ", date=_today, open=Decimal("150"), high=Decimal("152"),
                      low=Decimal("149"), close=Decimal("151"), adj_close=Decimal("151"), volume=100000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="JNJ", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("1.50"),
        strike=Decimal("160"), expiration_date=_today,  # OTM: close=151 < strike=160
        now=_open_date)
    # Also open underlying stock position (for cost basis in feedback)
    stock_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    await repo.open_position(
        rec_id=stock_rec_id, ticker="JNJ", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("148"),
        strike=None, expiration_date=None, now=_open_date)
    await session.commit()

    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    pos = await repo.get_position(pos_id)
    assert pos.status == "expired"
    trades = await repo.list_trades()
    assert any(t.position_id == pos_id and t.side == "expire" for t in trades)

    from sqlalchemy import select

    from app.models.portfolio import Feedback
    fb_rows = (await session.execute(
        select(Feedback).where(Feedback.recommendation_id == rec_id)
    )).scalars().all()
    assert len(fb_rows) == 1
    assert fb_rows[0].outcome == "win"
    assert fb_rows[0].exit_reason == "expiration"
    assert fb_rows[0].premiums_collected > 0


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_itm_call_assignment(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("CVX", "Chevron", "E", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="CVX", date=_today, open=Decimal("170"), high=Decimal("172"),
                      low=Decimal("169"), close=Decimal("171"), adj_close=Decimal("171"), volume=200000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    stock_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="CVX", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    stock_pos_id = await repo.open_position(
        rec_id=stock_rec_id, ticker="CVX", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("150"),
        strike=None, expiration_date=None, now=_open_date)
    call_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="CVX", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    call_pos_id = await repo.open_position(
        rec_id=call_rec_id, ticker="CVX", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("2.00"),
        strike=Decimal("160"), expiration_date=_today,  # ITM: close=171 >= strike=160
        now=_open_date)
    await session.commit()

    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    call_pos = await repo.get_position(call_pos_id)
    assert call_pos.status == "assigned"
    stock_pos = await repo.get_position(stock_pos_id)
    assert stock_pos.status == "assigned"
    events = await repo.list_income_events()
    # assignment_gain: (160 - 150) * 100 = 1000
    assert any(e.ticker == "CVX" and e.type == "assignment_gain" and e.amount == Decimal("1000") for e in events)
