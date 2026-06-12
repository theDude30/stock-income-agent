import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query

from app.analysis.portfolio import compute_adjusted_return_pct, compute_total_return_pct
from app.config import get_settings
from app.db import get_session_factory
from app.market.price_cache import PriceCache
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/portfolio")

# Test seam: set to a PriceCache instance to override production wiring.
_price_cache_override: PriceCache | None = None

# Process-global cache so the 120 s TTL spans requests.
_price_cache: PriceCache | None = None


def _fetch_live_price(ticker: str) -> Decimal:
    """Latest close from the market-data sources (honors pipeline's _sources_override)."""
    from app.api.pipeline import _make_sources
    since = datetime.now(tz=UTC).date() - timedelta(days=7)
    bars = list(_make_sources().prices.fetch(ticker, since))
    if not bars:
        raise LookupError(f"no recent price bars for {ticker}")
    return Decimal(str(bars[-1].close))


def _get_price_cache() -> PriceCache:
    global _price_cache
    if _price_cache_override is not None:
        return _price_cache_override
    if _price_cache is None:
        _price_cache = PriceCache(fetch=_fetch_live_price)
    return _price_cache


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


@router.get("/live")
async def live() -> dict:
    cache = _get_price_cache()
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        positions = await repo.list_open_positions(kind="stock")
        out = []
        for pos in positions:
            stale = False
            price: Decimal | None
            try:
                price, _ = await cache.get(pos.ticker)
            except Exception:
                close = await repo.latest_close(pos.ticker)
                price = Decimal(str(close)) if close is not None else None
                stale = True
            if price is not None:
                cost = pos.avg_entry_price * pos.shares
                live_pnl = (price - pos.avg_entry_price) * pos.shares
                live_pnl_pct = live_pnl / cost if cost > 0 else Decimal("0")
            else:
                live_pnl = None
                live_pnl_pct = None
            out.append({
                "id": pos.id,
                "ticker": pos.ticker,
                "shares": float(pos.shares),
                "avg_entry_price": float(pos.avg_entry_price),
                "live_price": float(price) if price is not None else None,
                "live_pnl": float(live_pnl) if live_pnl is not None else None,
                "live_pnl_pct": float(live_pnl_pct) if live_pnl_pct is not None else None,
                "stale": stale,
                "opened_at": pos.opened_at.isoformat(),
            })
        return {"as_of": datetime.now(tz=UTC).isoformat(), "positions": out}


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


def _spy_ytd_total_return_pct(ytd_start: date) -> float | None:
    """SPY total return from adjusted closes; None if the fetch fails or is empty."""
    from app.api.pipeline import _make_sources
    try:
        bars = list(_make_sources().prices.fetch("SPY", ytd_start))
    except Exception:
        return None
    if len(bars) < 2:
        return None
    start = Decimal(str(bars[0].adj_close))
    end = Decimal(str(bars[-1].adj_close))
    return float(compute_adjusted_return_pct(start, end))


@router.get("/performance")
async def performance() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        today = datetime.now(tz=UTC).date()
        ytd_start = date(today.year, 1, 1)

        events = await repo.list_income_events(from_=ytd_start, to=today)
        ytd_income = sum((Decimal(str(e.amount)) for e in events), Decimal("0"))

        positions = await repo.list_open_positions(kind="stock")
        cost_basis = Decimal("0")
        capital_pnl = Decimal("0")
        for p in positions:
            cost_basis += p.avg_entry_price * p.shares
            close = await repo.latest_close(p.ticker)
            if close is not None:
                capital_pnl += (Decimal(str(close)) - p.avg_entry_price) * p.shares

        # premiums are already income events (call_premium / assignment_gain),
        # so they're inside ytd_income; pass premiums=0 to avoid double counting.
        total_return_pct = compute_total_return_pct(
            capital_pnl=capital_pnl, dividends=ytd_income,
            premiums=Decimal("0"), cost_basis=cost_basis,
        )

        spy_total_return_pct = await asyncio.to_thread(_spy_ytd_total_return_pct, ytd_start)

        settings = get_settings()
        ytd_fraction = (today - ytd_start).days / 365
        treasury_ytd_return_pct = settings.treasury_1m_yield_pct / 100 * ytd_fraction

        return {
            "ytd_income": float(ytd_income),
            "cost_basis": float(cost_basis),
            "ytd_capital_pnl": float(capital_pnl),
            "ytd_total_return_pct": float(total_return_pct),
            "spy_total_return_pct": spy_total_return_pct,
            "treasury_1m_yield_pct": settings.treasury_1m_yield_pct,
            "treasury_ytd_return_pct": treasury_ytd_return_pct,
        }
