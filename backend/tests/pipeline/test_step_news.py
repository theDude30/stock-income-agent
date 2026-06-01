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
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_news_step_dedupes_by_url_across_runs(session, monkeypatch, pg_container):
    """Run the step twice with the same source data; second run should be a no-op due to URL UNIQUE."""
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from sqlalchemy import func, select

    from app.models.news import NewsItem
    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.news import NewsStep
    from app.sources.base import (
        DividendEvent,
        NewsItemDTO,
        PriceBar,
        Sources,
        StockMeta,
    )
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    # Use unique ticker name to avoid carryover.
    await repo.upsert_stocks([StockMeta("NEWSKO", "Coca-Cola test", None, None)], today=date(2026, 6, 1))
    # Seed price + dividend so the watchlist query picks up NEWSKO.
    await repo.upsert_prices(
        "NEWSKO", [PriceBar(date(2026, 6, 1), 60, 60, 60, 60, 60, 1000)]
    )
    await repo.upsert_dividends("NEWSKO", [DividendEvent(date(2026, 5, 15), None, 1.84)])
    await session.commit()

    unique_url = "https://example.com/newsko-unique-article-task12"
    same_item = NewsItemDTO(
        url=unique_url,
        title="NEWSKO test news",
        summary="...",
        source="yahoo",
        published_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({"NEWSKO": [same_item]}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    step = NewsStep(watchlist_size=10, concurrency=2, attempts=1)
    await step.run(ctx)
    await session.commit()
    await step.run(ctx)  # rerun
    await session.commit()

    # Count rows for this specific URL. Should be exactly 1 (idempotent).
    count = await session.execute(select(func.count(NewsItem.id)).where(NewsItem.url == unique_url))
    assert count.scalar_one() == 1
