from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/portfolio")


@router.get("/holdings")
async def holdings() -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        positions = await repo.list_open_positions(kind="stock")
        result = []
        for pos in positions:
            close = await repo.latest_close(pos.ticker)
            close_price = close
            unrealized_pnl = (
                float((close - float(pos.avg_entry_price)) * float(pos.shares))
                if close is not None else None
            )
            # find active covered call on this ticker
            calls = await repo.list_open_positions(ticker=pos.ticker, kind="short_call")
            active_call = None
            if calls:
                c = calls[0]
                active_call = {
                    "strike": float(c.strike) if c.strike is not None else None,
                    "expiration_date": c.expiration_date.isoformat() if c.expiration_date is not None else None,
                    "premium": float(c.avg_entry_price),
                }
            # get latest price date
            from sqlalchemy import select

            from app.models.stocks import Price
            price_row = (await session.execute(
                select(Price.date).where(Price.ticker == pos.ticker)
                .order_by(Price.date.desc()).limit(1)
            )).scalar()
            result.append({
                "id": pos.id,
                "ticker": pos.ticker,
                "shares": float(pos.shares),
                "avg_entry_price": float(pos.avg_entry_price),
                "current_price": close_price,
                "price_date": price_row.isoformat() if price_row else None,
                "unrealized_pnl": unrealized_pnl,
                "opened_at": pos.opened_at.isoformat(),
                "active_call": active_call,
            })
        return result


@router.get("/income")
async def income(
    from_: date | None = Query(None, alias="from"),  # noqa: B008
    to: date | None = None,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        events = await repo.list_income_events(from_=from_, to=to)
        return [
            {
                "id": e.id, "ticker": e.ticker, "type": e.type,
                "amount": float(e.amount), "event_date": e.event_date.isoformat(),
                "source_position_id": e.source_position_id,
            }
            for e in events
        ]


@router.get("/income/calendar")
async def income_calendar(days: int = 30) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from datetime import UTC, datetime
        today = datetime.now(UTC).date()
        cutoff = today + timedelta(days=days)

        # Upcoming dividends for held tickers
        held = await repo.list_open_positions(kind="stock")
        upcoming_dividends = []
        for pos in held:
            divs = await repo.dividends_since(pos.ticker, today - timedelta(days=1))
            for d in divs:
                if d.ex_date <= cutoff:
                    upcoming_dividends.append({
                        "ticker": pos.ticker,
                        "ex_date": d.ex_date.isoformat(),
                        "amount_per_share": float(d.amount_per_share),
                        "estimated_income": float(d.amount_per_share * pos.shares),
                    })

        # Calls expiring within N days
        calls = await repo.list_open_positions(kind="short_call")
        expiring_calls = [
            {
                "ticker": pos.ticker,
                "expiration_date": pos.expiration_date.isoformat() if pos.expiration_date else None,
                "strike": float(pos.strike) if pos.strike is not None else None,
                "premium": float(pos.avg_entry_price),
            }
            for pos in calls
            if pos.expiration_date and pos.expiration_date <= cutoff
        ]

        return {"upcoming_dividends": upcoming_dividends, "expiring_calls": expiring_calls}


@router.get("/performance")
async def performance() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from datetime import UTC, datetime
        today = datetime.now(UTC).date()
        ytd_start = date(today.year, 1, 1)

        events = await repo.list_income_events(from_=ytd_start, to=today)
        ytd_income = sum(float(e.amount) for e in events)

        positions = await repo.list_open_positions(kind="stock")
        cost_basis = sum(float(p.avg_entry_price) * float(p.shares) for p in positions)

        return {
            "ytd_income": ytd_income,
            "cost_basis": cost_basis,
            "note": "SPY total-return benchmark and Treasury baseline ship in Sub-project 5",
        }
