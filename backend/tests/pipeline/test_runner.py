import os
import subprocess
import sys
from datetime import UTC, datetime

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


def _make_ctx(session):
    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )
    return StepContext(
        repo=PipelineRepo(session),
        sources=Sources(
            universe=InMemoryUniverseSource([]),
            prices=InMemoryPriceSource({}),
            dividends=InMemoryDividendSource({}),
            options=InMemoryOptionsSource({}),
            news=InMemoryNewsSource({}),
        ),
        run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_records_success(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepResult

    class OkStep(Step):
        name = "ok"
        is_critical = False

        async def run(self, ctx):
            return StepResult(ok_count=42)

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[OkStep()])
    await session.commit()
    assert summary.status == "success"
    assert summary.steps_completed == ["ok"]

    run = await ctx.repo.get_run(summary.run_id)
    assert run is not None and run.status == "success"


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_records_partial_on_non_critical_failure(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepFailure, StepResult

    class OkStep(Step):
        name = "ok"
        is_critical = False
        async def run(self, ctx): return StepResult(ok_count=1)

    class FlakyStep(Step):
        name = "flaky"
        is_critical = False
        async def run(self, ctx):
            raise StepFailure("upstream returned 500")

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[OkStep(), FlakyStep()])
    await session.commit()
    assert summary.status == "partial"
    assert "flaky" in summary.errors
    assert summary.steps_completed == ["ok"]


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_stops_and_marks_failed_on_critical_failure(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepFailure, StepResult

    class CriticalFail(Step):
        name = "critical"
        is_critical = True
        async def run(self, ctx):
            raise StepFailure("prices below threshold")

    class Later(Step):
        name = "later"
        is_critical = False
        async def run(self, ctx):
            return StepResult(ok_count=999)  # should never run

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[CriticalFail(), Later()])
    await session.commit()
    assert summary.status == "failed"
    assert summary.steps_completed == []
    assert "later" not in summary.errors


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_skips_steps_with_should_run_false(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepResult

    class GatedStep(Step):
        name = "gated"
        is_critical = False
        async def should_run(self, ctx): return False
        async def run(self, ctx): return StepResult(ok_count=1)

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[GatedStep()])
    await session.commit()
    assert summary.status == "success"
    assert summary.steps_completed == []
