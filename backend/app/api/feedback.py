from datetime import date

from fastapi import APIRouter, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


def _feedback(row) -> dict:
    return {
        "id": row.id,
        "recommendation_id": row.recommendation_id,
        "position_id": row.position_id,
        "entry_price": float(row.entry_price),
        "exit_price": float(row.exit_price) if row.exit_price is not None else None,
        "capital_pnl": float(row.capital_pnl),
        "dividends_received": float(row.dividends_received),
        "premiums_collected": float(row.premiums_collected),
        "total_return_pct": float(row.total_return_pct),
        "held_days": row.held_days,
        "outcome": row.outcome,
        "exit_reason": row.exit_reason,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/feedback")
async def list_feedback(
    from_: date | None = Query(None, alias="from"),  # noqa: B008
    to: date | None = None,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_feedback(from_=from_, to=to)
        return [_feedback(r) for r in rows]
