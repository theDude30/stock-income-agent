import os

import pytest

from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.prompts import SAFETY_PROMPT_VERSION, SAFETY_SYSTEM, build_safety_prompt
from app.llm.schemas import SafetyAssessment


@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
def test_real_safety_call_returns_valid_schema():
    client = AnthropicLLMClient(model="claude-sonnet-4-6", api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = build_safety_prompt(
        ticker="KO",
        metrics={"payout_ratio": 0.68, "fcf_coverage": 1.4, "debt_to_equity": 1.6},
        recent_dividends=["2026-03-15: 0.485"],
        recent_news=["Coca-Cola reports steady volume growth"],
        active_lessons=[],
    )
    assessment, usage = client.complete_structured(
        system=SAFETY_SYSTEM, prompt=prompt, schema=SafetyAssessment,
        prompt_version=SAFETY_PROMPT_VERSION, key="KO",
    )
    assert isinstance(assessment, SafetyAssessment)
    assert 0 <= assessment.score <= 100
    assert usage.input_tokens > 0
    assert usage.cost_usd > 0
