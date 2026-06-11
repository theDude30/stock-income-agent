from datetime import date
from typing import Literal

from pydantic import BaseModel


class SafetyAssessment(BaseModel):
    score: int
    concerns: list[str]
    outlook: Literal["improving", "stable", "deteriorating"]
    reasoning: str


class CallPick(BaseModel):
    strike: float
    expiration_date: date
    expected_premium: float
    prob_assignment: float
    reasoning: str


class ProposedLesson(BaseModel):
    pattern: str
    sample_size: int
    evidence_recommendation_ids: list[int]
    contradicts_lesson_id: int | None = None


class LessonRetirement(BaseModel):
    lesson_id: int
    reason: str


class LearnerOutput(BaseModel):
    new_lessons: list[ProposedLesson]
    retirements: list[LessonRetirement]
