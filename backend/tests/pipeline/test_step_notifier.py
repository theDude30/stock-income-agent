import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory
from app.notify.email import FakeEmailSender, NullEmailSender
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.notifier import NotifierStep
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


_now = datetime(2026, 6, 9, 17, 20, tzinfo=UTC)  # not the 1st -> no monthly summary
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, email):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now, email=email)


@pytest.mark.asyncio(loop_scope="session")
async def test_notifier_writes_web_alerts_and_emails(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)

    # one pending rec in this run -> new_recommendations alert
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    # an open stock position + an upcoming dividend -> dividend_payment_upcoming
    await repo.open_position(rec_id=rec_id, ticker="KO", kind="stock", shares=Decimal("100"),
                             avg_entry_price=Decimal("60"), strike=None, expiration_date=None, now=_now)
    session.add(DividendHistory(ticker="KO", ex_date=date(2026, 6, 12), pay_date=None,
                                amount_per_share=Decimal("0.485"), frequency="quarterly"))
    # a call expiring in 3 days -> call_expiring
    call_rec = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(rec_id=call_rec, ticker="KO", kind="short_call", shares=Decimal("1"),
                             avg_entry_price=Decimal("1.20"), strike=Decimal("65"),
                             expiration_date=date(2026, 6, 12), now=_now)
    await session.flush()

    email = FakeEmailSender()
    result = await NotifierStep().run(_ctx(repo, run_id, email))
    await session.commit()

    alerts = await repo.list_alerts(run_id=run_id)
    types = {a.type for a in alerts if a.channel == "web"}
    assert {"new_recommendations", "dividend_payment_upcoming", "call_expiring"} <= types
    # email enabled -> a single email-channel alert with sent_at, and one email sent
    email_rows = [a for a in alerts if a.channel == "email"]
    assert len(email_rows) == 1 and email_rows[0].sent_at is not None
    assert len(email.sent) == 1
    assert result.ok_count >= 3


@pytest.mark.asyncio(loop_scope="session")
async def test_notifier_no_email_when_null_sender_and_idempotent(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(rec_id=rec_id, ticker="PG", kind="stock", shares=Decimal("50"),
                             avg_entry_price=Decimal("150"), strike=None, expiration_date=None, now=_now)
    await session.flush()

    await NotifierStep().run(_ctx(repo, run_id, NullEmailSender()))
    await session.commit()
    first = await repo.list_alerts(run_id=run_id)
    assert all(a.channel == "web" for a in first)  # no email channel rows

    # re-run replaces, does not duplicate
    await NotifierStep().run(_ctx(repo, run_id, NullEmailSender()))
    await session.commit()
    second = await repo.list_alerts(run_id=run_id)
    assert len(second) == len(first)
