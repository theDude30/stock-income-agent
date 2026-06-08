import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.sources.base import FundamentalsSnapshot, StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_fundamentals_and_recs_roundtrip(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "Staples", "Beverages")], today=_now().date())

    await repo.upsert_fundamentals("KO", [FundamentalsSnapshot(
        "2026Q1", revenue=100.0, eps=2.0, fcf=30.0, net_income=20.0,
        total_debt=50.0, total_equity=80.0, dividends_paid=10.0)])
    funds = await repo.latest_fundamentals("KO")
    assert funds is not None and float(funds.net_income) == 20.0

    run_id = await repo.start_run(now=_now())
    await repo.insert_screening(run_id, "KO", score=82.5, signals={"ttm_yield": 0.03}, passed=True, now=_now())
    screenings = await repo.get_screenings(run_id)
    assert len(screenings) == 1 and screenings[0].ticker == "KO"
    top = await repo.top_screened_tickers(run_id, limit=10)
    assert top == ["KO"]

    await repo.insert_safety_score("KO", score=80, payout_ratio=0.5, fcf_coverage=3.0,
                                   debt_to_equity=0.4, consecutive_years_paid=30, concerns=["x"],
                                   reasoning="r", model="claude-sonnet-4-6", prompt_version="safety-v1", now=_now())
    latest = await repo.latest_safety_score("KO")
    assert latest is not None and latest.score == 80

    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 10}, reasoning="solid", signals_snapshot={"score": 82.5},
        model="claude-sonnet-4-6", prompt_version="safety-v1", now=_now())
    rec = await repo.get_recommendation(rec_id)
    assert rec.status == "pending" and rec.type == "add_position"

    listed = await repo.list_recommendations(status="pending", type_=None)
    assert any(r.id == rec_id for r in listed)

    await repo.add_llm_usage(run_id, tokens=1500, cost=0.012)
    run = await repo.get_run(run_id)
    assert run.llm_tokens_used == 1500
    await session.commit()
