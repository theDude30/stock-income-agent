from app.llm.base import FakeLLMClient, LLMUsage
from app.pipeline.steps.base import StepContext


def test_step_context_accepts_llm():
    llm = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0))
    ctx = StepContext(repo=None, sources=None, run_id=1, llm=llm)
    assert ctx.llm is llm


def test_step_context_llm_defaults_none():
    ctx = StepContext(repo=None, sources=None, run_id=1)
    assert ctx.llm is None
