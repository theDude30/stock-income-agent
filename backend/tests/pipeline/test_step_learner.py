import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import LearnerOutput, ProposedLesson
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.learner import LearnerStep
from app.sources.base import Sources


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


_now = datetime(2026, 6, 12, 17, 30, tzinfo=UTC)  # a Friday
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, llm):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now, llm=llm)


@pytest.mark.asyncio(loop_scope="session")
async def test_learner_adopts_gates_and_retires(session):
    repo = PipelineRepo(session)
    # an existing active lesson that will be contradicted by a larger-sample proposal
    old_id = await repo.insert_lesson("Small sample lesson to be superseded later", [1], 5, _now)
    run_id = await repo.start_run(now=_now)

    output = LearnerOutput(
        new_lessons=[
            ProposedLesson(pattern="REITs above 95% payout cut within two quarters reliably",
                           sample_size=7, evidence_recommendation_ids=[10, 11]),
            ProposedLesson(pattern="too short", sample_size=9, evidence_recommendation_ids=[]),  # fails falsifiability
            ProposedLesson(pattern="Low sample idea that should be dropped by the gate here",
                           sample_size=3, evidence_recommendation_ids=[]),  # fails sample size
            ProposedLesson(pattern="Bigger-sample replacement for the superseded lesson here now",
                           sample_size=9, evidence_recommendation_ids=[12],
                           contradicts_lesson_id=old_id),  # supersedes old_id
        ],
        retirements=[],
    )
    llm = FakeLLMClient(by_key={"learner": output}, usage=LLMUsage(10, 10, 0.001))

    result = await LearnerStep().run(_ctx(repo, run_id, llm))
    await session.commit()

    active = await repo.active_lessons()
    assert "REITs above 95% payout cut within two quarters reliably" in active
    assert "Bigger-sample replacement for the superseded lesson here now" in active
    assert "too short" not in active
    assert "Low sample idea that should be dropped by the gate here" not in active
    # the contradicted lesson was retired
    old = await repo.get_lesson(old_id)
    assert old.effective_until is not None
    assert "Small sample lesson to be superseded later" not in active
    assert result.ok_count == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_learner_noop_without_llm(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now)
    result = await LearnerStep().run(_ctx(repo, run_id, None))
    assert result.ok_count == 0
