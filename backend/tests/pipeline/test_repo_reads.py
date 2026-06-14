import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory, Price
from app.pipeline.repo import PipelineRepo
from app.sources.base import NewsItemDTO, StockMeta


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


_now = datetime(2026, 6, 11, 17, 15, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_stock(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    stock = await repo.get_stock("ADP")
    assert stock is not None and stock.name == "Automatic Data Processing"
    assert await repo.get_stock("NOPE") is None
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_between(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    for d, close in [(date(2026, 6, 8), "300"), (date(2026, 6, 9), "302"), (date(2026, 6, 10), "301")]:
        session.add(Price(ticker="ADP", date=d, open=Decimal(close), high=Decimal(close),
                          low=Decimal(close), close=Decimal(close), adj_close=Decimal(close),
                          volume=1000))
    await session.flush()

    all_rows = await repo.prices_between("ADP")
    assert [p.date for p in all_rows] == [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]  # asc

    windowed = await repo.prices_between("ADP", from_=date(2026, 6, 9), to=date(2026, 6, 9))
    assert len(windowed) == 1 and windowed[0].close == Decimal("302")
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_dividend_history_newest_first(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    session.add(DividendHistory(ticker="ADP", ex_date=date(2026, 3, 10), pay_date=None,
                                amount_per_share=Decimal("1.40"), frequency="quarterly"))
    session.add(DividendHistory(ticker="ADP", ex_date=date(2026, 6, 10), pay_date=None,
                                amount_per_share=Decimal("1.40"), frequency="quarterly"))
    await session.flush()

    divs = await repo.list_dividend_history("ADP")
    assert [d.ex_date for d in divs] == [date(2026, 6, 10), date(2026, 3, 10)]  # desc
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_news_newest_first_with_limit(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    items = [
        NewsItemDTO(url=f"https://example.com/adp/{i}", title=f"ADP story {i}", summary="s",
                    source="example", published_at=datetime(2026, 6, 1 + i, tzinfo=UTC))
        for i in range(3)
    ]
    await repo.insert_news("ADP", items)

    news = await repo.list_news("ADP", limit=2)
    assert len(news) == 2
    assert news[0].published_at > news[1].published_at  # desc
    assert news[0].title == "ADP story 2"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_latest_screening(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    run_id = await repo.start_run(now=_now)
    await repo.insert_screening(run_id, "ADP", 70.0, {"k": 1}, True,
                                datetime(2026, 6, 10, tzinfo=UTC))
    await repo.insert_screening(run_id, "ADP", 75.0, {"k": 2}, True,
                                datetime(2026, 6, 11, tzinfo=UTC))

    latest = await repo.latest_screening("ADP")
    assert latest is not None and latest.dividend_quality_score == Decimal("75.00")
    assert await repo.latest_screening("NOPE") is None
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_history_desc_with_limit(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    for day, score in [(9, 80), (10, 82), (11, 85)]:
        await repo.insert_safety_score("ADP", score, 0.5, 2.0, 0.4, 25, [], "fine",
                                       "m", "v", datetime(2026, 6, day, tzinfo=UTC))

    history = await repo.safety_score_history("ADP", limit=2)
    assert [s.score for s in history] == [85, 82]  # newest first, limited
    await session.commit()
