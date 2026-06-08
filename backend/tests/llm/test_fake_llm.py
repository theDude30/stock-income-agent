import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import SafetyAssessment


def test_fake_returns_canned_and_usage():
    canned = SafetyAssessment(score=80, concerns=["payout rising"], outlook="stable", reasoning="ok")
    client = FakeLLMClient(by_key={"KO": canned}, usage=LLMUsage(100, 50, 0.001))

    parsed, usage = client.complete_structured(
        system="s", prompt="p", schema=SafetyAssessment, prompt_version="safety-v1", key="KO",
    )
    assert parsed == canned
    assert usage == LLMUsage(100, 50, 0.001)


def test_fake_invalid_mode_raises():
    client = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0), raise_for={"BAD"})
    with pytest.raises(ValueError):
        client.complete_structured(
            system="s", prompt="p", schema=SafetyAssessment, prompt_version="v", key="BAD",
        )
