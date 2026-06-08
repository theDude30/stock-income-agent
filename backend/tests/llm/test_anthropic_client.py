from types import SimpleNamespace

import pytest

from app.llm.anthropic_client import AnthropicLLMClient, compute_cost_usd
from app.llm.schemas import SafetyAssessment


def test_compute_cost_sonnet():
    # 1M input @ $3, 1M output @ $15
    assert compute_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_complete_structured_parses_and_computes_usage(monkeypatch):
    parsed = SafetyAssessment(score=70, concerns=[], outlook="stable", reasoning="r")
    fake_response = SimpleNamespace(
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
    )

    class FakeMessages:
        def parse(self, **kwargs):
            assert kwargs["model"] == "claude-sonnet-4-6"
            assert kwargs["output_format"] is SafetyAssessment
            return fake_response

    client = AnthropicLLMClient(model="claude-sonnet-4-6", api_key="x")
    client._client = SimpleNamespace(messages=FakeMessages())  # inject fake SDK

    out, usage = client.complete_structured(
        system="s", prompt="p", schema=SafetyAssessment, prompt_version="safety-v1", key="KO",
    )
    assert out == parsed
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cost_usd == pytest.approx(1000 / 1e6 * 3 + 500 / 1e6 * 15)
