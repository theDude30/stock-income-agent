import os
import subprocess
import sys
from datetime import UTC, datetime
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


_now = datetime(2026, 6, 9, 17, 30, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_lesson_lifecycle(session):
    repo = PipelineRepo(session)
    lid = await repo.insert_lesson("Utilities with high leverage cut in rate cycles", [1, 2], 6, _now)
    assert lid > 0
    assert "Utilities with high leverage cut in rate cycles" in await repo.active_lessons()

    # ignore suppresses from active_lessons but keeps the row listed
    updated = await repo.set_lesson_ignored(lid, True)
    assert updated is not None and updated.user_ignored is True
    assert "Utilities with high leverage cut in rate cycles" not in await repo.active_lessons()
    assert any(x.id == lid for x in await repo.list_lessons(active=False))

    # un-ignore then retire
    await repo.set_lesson_ignored(lid, False)
    await repo.retire_lesson(lid, "no longer supported", _now)
    assert "Utilities with high leverage cut in rate cycles" not in await repo.active_lessons()
    row = await repo.get_lesson(lid)
    assert row.effective_until is not None and row.retired_reason == "no longer supported"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_alert_delete_then_insert_idempotency(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now)
    await repo.insert_alert(run_id, "call_expiring", {"ticker": "KO"}, "web", None, _now)
    assert len(await repo.list_alerts(run_id=run_id)) == 1
    await repo.delete_alerts_for_run(run_id)
    await repo.insert_alert(run_id, "call_expiring", {"ticker": "KO"}, "web", None, _now)
    assert len(await repo.list_alerts(run_id=run_id)) == 1
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_delta_and_cost_mtd(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PEP", "Pepsi", "S", "B")], today=_today)
    assert await repo.safety_score_delta("PEP") is None  # < 2 scores
    await repo.insert_safety_score(
        ticker="PEP", score=80, payout_ratio=None, fcf_coverage=None, debt_to_equity=None,
        consecutive_years_paid=None, concerns=[], reasoning="r", model="m",
        prompt_version="v", now=datetime(2026, 6, 1, tzinfo=UTC))
    await repo.insert_safety_score(
        ticker="PEP", score=66, payout_ratio=None, fcf_coverage=None, debt_to_equity=None,
        consecutive_years_paid=None, concerns=["margin pressure"], reasoning="r", model="m",
        prompt_version="v", now=datetime(2026, 6, 8, tzinfo=UTC))
    assert await repo.safety_score_delta("PEP") == (66, 80)

    cost = await repo.llm_cost_month_to_date(_today)
    assert cost >= Decimal("0")
    await session.commit()
