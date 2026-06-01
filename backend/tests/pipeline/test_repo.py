import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


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
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_upsert_stocks_inserts_new_and_updates_existing(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple Inc.", "Tech", "Consumer Electronics")],
        today=date(2026, 6, 1),
    )
    # Re-run with a name change
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", "Tech", "Consumer Electronics")],
        today=date(2026, 6, 1),
    )
    await session.commit()
    rows = await repo.list_active_tickers()
    assert rows == ["AAPL"]


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_deactivates_missing_tickers(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", None, None), StockMeta("MSFT", "Microsoft", None, None)],
        today=date(2026, 6, 1),
    )
    await session.commit()

    # Second sync: only AAPL remains. MSFT should be deactivated.
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", None, None)],
        today=date(2026, 6, 2),
    )
    await session.commit()

    active = await repo.list_active_tickers()
    assert "AAPL" in active
    assert "MSFT" not in active


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_upsert_prices_idempotent(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import PriceBar, StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("GOOG", "Alphabet", None, None)], today=date(2026, 6, 1))
    bars = [
        PriceBar(date(2026, 6, 1), 150.0, 151.0, 149.0, 150.5, 150.5, 1_000_000),
        PriceBar(date(2026, 6, 2), 150.5, 152.0, 150.0, 151.0, 151.0, 1_500_000),
    ]
    await repo.upsert_prices("GOOG", bars)
    await repo.upsert_prices("GOOG", bars)  # rerun
    await session.commit()

    last_date = await repo.last_price_date("GOOG")
    assert last_date == date(2026, 6, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_start_and_finish_run(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo

    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=datetime(2026, 6, 1, 21, 15, tzinfo=UTC))
    await session.commit()
    assert run_id > 0

    await repo.finish_run(
        run_id,
        status="success",
        completed=["universe", "prices"],
        errors={},
        now=datetime(2026, 6, 1, 21, 17, tzinfo=UTC),
    )
    await session.commit()

    runs = await repo.recent_runs(limit=1)
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].steps_completed == ["universe", "prices"]
