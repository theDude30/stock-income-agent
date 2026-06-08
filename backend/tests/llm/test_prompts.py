from app.llm.prompts import (
    SAFETY_PROMPT_VERSION,
    SAFETY_SYSTEM,
    build_safety_prompt,
)


def test_build_safety_prompt_includes_metrics_and_empty_lessons():
    prompt = build_safety_prompt(
        ticker="KO",
        metrics={"payout_ratio": 0.5, "fcf_coverage": 2.0, "debt_to_equity": 0.4},
        recent_dividends=["2026-03-15: 0.46"],
        recent_news=["Coca-Cola raises guidance"],
        active_lessons=[],  # empty until Sub-project 5
    )
    assert "KO" in prompt
    assert "payout_ratio" in prompt
    assert "Coca-Cola raises guidance" in prompt
    assert SAFETY_PROMPT_VERSION == "safety-v1"
    assert "safety analyst" in SAFETY_SYSTEM.lower()
