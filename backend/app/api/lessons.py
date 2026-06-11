from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/lessons")


class IgnoreBody(BaseModel):
    ignored: bool = True


def _lesson(row) -> dict:
    return {
        "id": row.id,
        "pattern": row.pattern,
        "sample_size": row.sample_size,
        "evidence_recommendation_ids": list(row.evidence_recommendation_ids or []),
        "effective_from": row.effective_from.isoformat(),
        "effective_until": row.effective_until.isoformat() if row.effective_until is not None else None,
        "user_ignored": row.user_ignored,
        "retired_reason": row.retired_reason,
    }


@router.get("")
async def list_lessons(active: bool = True) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_lessons(active=active)
        return [_lesson(r) for r in rows]


@router.post("/{lesson_id}/ignore")
async def ignore_lesson(lesson_id: int, body: IgnoreBody) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        updated = await repo.set_lesson_ignored(lesson_id, body.ignored)
        if updated is None:
            raise HTTPException(status_code=404, detail="lesson not found")
        await session.commit()
        return _lesson(updated)
