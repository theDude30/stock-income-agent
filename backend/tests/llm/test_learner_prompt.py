from app.llm.prompts import LEARNER_PROMPT_VERSION, build_learner_prompt
from app.llm.schemas import LearnerOutput, LessonRetirement, ProposedLesson


def test_learner_prompt_includes_evidence_and_lessons():
    prompt = build_learner_prompt(
        active_lessons=["Old lesson about utilities"],
        feedback=[{"ticker": "KO", "outcome": "win", "total_return_pct": "0.03"}],
        income_events=[{"ticker": "KO", "type": "dividend", "amount": "48.5"}],
        safety_deltas=[{"ticker": "PEP", "current": 66, "previous": 80}],
        rejections=[{"ticker": "T", "type": "add_position"}],
    )
    assert "Old lesson about utilities" in prompt
    assert "KO" in prompt and "PEP" in prompt
    assert LEARNER_PROMPT_VERSION == "learner-v1"


def test_learner_output_schema():
    out = LearnerOutput(
        new_lessons=[ProposedLesson(pattern="x", sample_size=6, evidence_recommendation_ids=[1])],
        retirements=[LessonRetirement(lesson_id=3, reason="stale")],
    )
    assert out.new_lessons[0].sample_size == 6
    assert out.new_lessons[0].contradicts_lesson_id is None
    assert out.retirements[0].lesson_id == 3
