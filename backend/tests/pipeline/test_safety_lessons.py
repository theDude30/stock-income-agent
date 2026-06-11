import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import SafetyAssessment
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.safety import SafetyStep
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


class CapturingLLM(FakeLLMClient):
    def __init__(self, by_key, usage):
        super().__init__(by_key=by_key, usage=usage)
        self.prompts: list[str] = []

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        self.prompts.append(prompt)
        return super().complete_structured(
            system=system, prompt=prompt, schema=schema, prompt_version=prompt_version, key=key)


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_prompt_includes_active_lessons(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("MMM", "3M", "I", "B")], today=_today)
    await repo.insert_lesson("Industrials with falling FCF coverage cut within a year", [1], 6, _now)
    run_id = await repo.start_run(now=_now)
    # screen MMM so SafetyStep picks it up as a finalist (top_screened_tickers)
    await repo.insert_screening(run_id, "MMM", 80, {}, True, _now)
    await session.flush()

    assessment = SafetyAssessment(score=72, concerns=[], outlook="stable", reasoning="ok")
    llm = CapturingLLM(by_key={"MMM": assessment}, usage=LLMUsage(5, 5, 0.0005))
    await SafetyStep().run(StepContext(repo=repo, sources=_sources, run_id=run_id,
                                       now=lambda: _now, llm=llm))
    await session.commit()
    assert any("Industrials with falling FCF coverage cut within a year" in p for p in llm.prompts)
