from fastapi import APIRouter, HTTPException

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


@router.get("/stocks/{ticker}/safety-score")
async def safety_score(ticker: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        s = await repo.latest_safety_score(ticker)
        if s is None:
            raise HTTPException(status_code=404, detail="no safety score for ticker")
        return {
            "ticker": s.ticker, "score": s.score,
            "payout_ratio": float(s.payout_ratio) if s.payout_ratio is not None else None,
            "fcf_coverage": float(s.fcf_coverage) if s.fcf_coverage is not None else None,
            "debt_to_equity": float(s.debt_to_equity) if s.debt_to_equity is not None else None,
            "consecutive_years_paid": s.consecutive_years_paid,
            "concerns": list(s.concerns or []),
            "reasoning": s.llm_reasoning, "llm_model": s.llm_model,
            "llm_prompt_version": s.llm_prompt_version, "scored_at": s.scored_at.isoformat(),
        }


@router.get("/screenings")
async def screenings(run_id: int | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        if run_id is None:
            run_id = await repo.latest_screening_run_id()
        if run_id is None:
            return []
        rows = await repo.get_screenings(run_id)
        return [
            {"ticker": r.ticker, "dividend_quality_score": float(r.dividend_quality_score),
             "passed_screen": r.passed_screen, "signals": r.signals,
             "created_at": r.created_at.isoformat()}
            for r in rows
        ]
