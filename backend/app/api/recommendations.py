from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/recommendations")


class RejectBody(BaseModel):
    reason: str | None = None


def _summary(r) -> dict:
    return {
        "id": r.id, "run_id": r.run_id, "type": r.type, "ticker": r.ticker,
        "confidence": r.confidence, "status": r.status,
        "created_at": r.created_at.isoformat(),
    }


def _full(r) -> dict:
    out = _summary(r)
    out.update({
        "payload": r.payload, "reasoning": r.reasoning,
        "signals_snapshot": r.signals_snapshot, "llm_model": r.llm_model,
        "llm_prompt_version": r.llm_prompt_version,
        "approval_mode": r.approval_mode, "decided_by": r.decided_by,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    })
    return out


@router.get("")
async def list_recommendations(status: str | None = "pending", type: str | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_recommendations(status=status, type_=type)
        return [_summary(r) for r in rows]


@router.get("/{rec_id}")
async def get_recommendation(rec_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rec = await repo.get_recommendation(rec_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="recommendation not found")
        return _full(rec)


@router.post("/{rec_id}/approve")
async def approve(rec_id: int) -> dict:
    return await _decide(rec_id, status="approved")


@router.post("/{rec_id}/reject")
async def reject(rec_id: int, body: RejectBody | None = None) -> dict:
    return await _decide(rec_id, status="rejected", reason=(body.reason if body else None))


async def _decide(rec_id: int, status: str, reason: str | None = None) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rec = await repo.get_recommendation(rec_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="recommendation not found")
        ok = await repo.set_recommendation_status(
            rec_id, status=status, decided_by="user", now=datetime.now(tz=UTC), reject_reason=reason)
        if not ok:
            raise HTTPException(status_code=409, detail=f"recommendation is not pending (status={rec.status})")
        await session.commit()
        updated = await repo.get_recommendation(rec_id)
        return _full(updated)
