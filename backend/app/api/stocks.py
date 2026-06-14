from datetime import date

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/stocks/{ticker}")
async def stock_detail(ticker: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        stock = await repo.get_stock(ticker)
        if stock is None:
            raise HTTPException(status_code=404, detail="unknown ticker")
        screening = await repo.latest_screening(ticker)
        safety = await repo.latest_safety_score(ticker)
        return {
            "ticker": stock.ticker, "name": stock.name, "sector": stock.sector,
            "industry": stock.industry, "active": stock.active,
            "latest_screening": {
                "dividend_quality_score": float(screening.dividend_quality_score),
                "passed_screen": screening.passed_screen,
                "signals": screening.signals,
                "created_at": screening.created_at.isoformat(),
            } if screening is not None else None,
            "latest_safety_score": {
                "score": safety.score,
                "concerns": list(safety.concerns or []),
                "reasoning": safety.llm_reasoning,
                "scored_at": safety.scored_at.isoformat(),
            } if safety is not None else None,
        }


@router.get("/stocks/{ticker}/prices")
async def stock_prices(
    ticker: str,
    from_: date | None = Query(None, alias="from"),  # noqa: B008
    to: date | None = None,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.prices_between(ticker, from_=from_, to=to)
        return [
            {"date": p.date.isoformat(), "open": float(p.open), "high": float(p.high),
             "low": float(p.low), "close": float(p.close), "adj_close": float(p.adj_close),
             "volume": p.volume}
            for p in rows
        ]


@router.get("/stocks/{ticker}/dividends")
async def stock_dividends(ticker: str) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_dividend_history(ticker)
        return [
            {"ex_date": d.ex_date.isoformat(),
             "pay_date": d.pay_date.isoformat() if d.pay_date is not None else None,
             "amount_per_share": float(d.amount_per_share),
             "frequency": d.frequency}
            for d in rows
        ]


@router.get("/stocks/{ticker}/news")
async def stock_news(ticker: str, limit: int = 20) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_news(ticker, limit=limit)
        return [
            {"id": n.id, "published_at": n.published_at.isoformat(), "source": n.source,
             "url": n.url, "title": n.title, "summary": n.summary,
             "sentiment_score": float(n.sentiment_score) if n.sentiment_score is not None else None}
            for n in rows
        ]


@router.get("/stocks/{ticker}/safety-score/history")
async def safety_score_history(ticker: str, limit: int = 20) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.safety_score_history(ticker, limit=limit)
        return [
            {"score": s.score, "concerns": list(s.concerns or []),
             "scored_at": s.scored_at.isoformat()}
            for s in rows
        ]


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
