from datetime import date

from fastapi import APIRouter, HTTPException

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


@router.get("/trades")
async def list_trades(from_: date | None = None, to: date | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        trades = await repo.list_trades(from_=from_, to=to)
        return [
            {
                "id": t.id, "position_id": t.position_id, "ticker": t.ticker,
                "side": t.side, "shares_or_contracts": float(t.shares_or_contracts),
                "price": float(t.price), "executed_at": t.executed_at.isoformat(),
                "reason": t.reason,
            }
            for t in trades
        ]


@router.get("/positions")
async def list_positions(status: str | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from sqlalchemy import select
        from app.models.portfolio import Position
        stmt = select(Position)
        if status is not None:
            stmt = stmt.where(Position.status == status)
        rows = await session.execute(stmt)
        positions = list(rows.scalars().all())
        return [_pos_summary(p) for p in positions]


@router.get("/positions/{position_id}")
async def get_position(position_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        pos = await repo.get_position(position_id)
        if pos is None:
            raise HTTPException(status_code=404, detail="position not found")
        trades = await repo.list_trades()
        pos_trades = [
            {
                "id": t.id, "side": t.side,
                "shares_or_contracts": float(t.shares_or_contracts),
                "price": float(t.price), "executed_at": t.executed_at.isoformat(),
                "reason": t.reason,
            }
            for t in trades if t.position_id == position_id
        ]
        events = await repo.list_income_events()
        pos_events = [
            {"id": e.id, "type": e.type, "amount": float(e.amount),
             "event_date": e.event_date.isoformat()}
            for e in events if e.source_position_id == position_id
        ]
        detail = _pos_summary(pos)
        detail["trades"] = pos_trades
        detail["income_events"] = pos_events
        return detail


def _pos_summary(pos) -> dict:
    return {
        "id": pos.id, "ticker": pos.ticker, "kind": pos.kind,
        "shares": float(pos.shares), "avg_entry_price": float(pos.avg_entry_price),
        "strike": float(pos.strike) if pos.strike is not None else None,
        "expiration_date": pos.expiration_date.isoformat() if pos.expiration_date is not None else None,
        "opened_at": pos.opened_at.isoformat(), "status": pos.status,
        "closed_at": pos.closed_at.isoformat() if pos.closed_at is not None else None,
    }
