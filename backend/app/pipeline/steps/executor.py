import logging
from datetime import date
from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_capital_pnl,
    compute_total_return_pct,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class ExecutorStep(Step):
    name = "executor"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        recs = await ctx.repo.approved_unexecuted_recs()
        ok, failures = 0, {}
        today = ctx.now().date()

        for rec in recs:
            try:
                if rec.type == "add_position":
                    await self._execute_add(ctx, rec, today)
                elif rec.type == "sell_covered_call":
                    await self._execute_sell_call(ctx, rec, today)
                elif rec.type == "sell_position":
                    await self._execute_sell_position(ctx, rec, today)
                else:
                    logger.info("executor: skipping unimplemented rec type %s", rec.type)
                    continue
                ok += 1
            except Exception as exc:
                logger.warning("executor: failed %s %s: %s", rec.type, rec.ticker, exc)
                failures[rec.ticker] = str(exc)

        return StepResult(ok_count=ok, per_ticker_failures=failures)

    async def _execute_add(self, ctx: StepContext, rec, today: date) -> None:
        price = await ctx.repo.latest_close(rec.ticker)
        if price is None:
            raise ValueError(f"no close price for {rec.ticker}")
        payload = rec.payload or {}
        shares = Decimal(str(payload.get("target_shares", 10)))
        price_dec = Decimal(str(price))

        position_id = await ctx.repo.open_position(
            rec_id=rec.id, ticker=rec.ticker, kind="stock",
            shares=shares, avg_entry_price=price_dec,
            strike=None, expiration_date=None, now=ctx.now(),
        )
        await ctx.repo.insert_trade(
            position_id=position_id, ticker=rec.ticker, side="buy",
            shares_or_contracts=shares, price=price_dec,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)

    async def _execute_sell_call(self, ctx: StepContext, rec, today: date) -> None:
        payload = rec.payload or {}
        premium = Decimal(str(payload.get("expected_premium", "0")))
        strike = Decimal(str(payload["strike"]))
        expiration = date.fromisoformat(str(payload["expiration_date"]))

        position_id = await ctx.repo.open_position(
            rec_id=rec.id, ticker=rec.ticker, kind="short_call",
            shares=Decimal("1"), avg_entry_price=premium,
            strike=strike, expiration_date=expiration, now=ctx.now(),
        )
        await ctx.repo.insert_trade(
            position_id=position_id, ticker=rec.ticker, side="sell_to_open",
            shares_or_contracts=Decimal("1"), price=premium,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.insert_income_event(
            ticker=rec.ticker, type_="call_premium",
            amount=premium * 100,  # 1 contract = 100 shares
            event_date=today,
            source_position_id=position_id,
            source_recommendation_id=rec.id,
            now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)

    async def _execute_sell_position(self, ctx: StepContext, rec, today: date) -> None:
        payload = rec.payload or {}
        position_id = payload.get("position_id")
        if position_id is None:
            raise ValueError(f"sell_position rec {rec.id} missing payload.position_id")

        pos = await ctx.repo.get_position(int(position_id))
        if pos is None or pos.status != "open":
            raise ValueError(f"position {position_id} not found or not open")

        price = await ctx.repo.latest_close(rec.ticker)
        if price is None:
            raise ValueError(f"no close price for {rec.ticker}")
        price_dec = Decimal(str(price))

        capital_pnl = compute_capital_pnl(pos.avg_entry_price, price_dec, pos.shares)
        cost_basis = pos.avg_entry_price * pos.shares
        total_return_pct = compute_total_return_pct(capital_pnl, Decimal(0), Decimal(0), cost_basis)
        held_days = (today - pos.opened_at.date()).days
        outcome = classify_outcome(total_return_pct)

        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=rec.ticker, side="sell",
            shares_or_contracts=pos.shares, price=price_dec,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "closed", ctx.now())
        await ctx.repo.insert_feedback(
            rec_id=rec.id, position_id=pos.id,
            entry_price=pos.avg_entry_price, exit_price=price_dec,
            capital_pnl=capital_pnl, dividends_received=Decimal(0),
            premiums_collected=Decimal(0), total_return_pct=total_return_pct,
            held_days=held_days, outcome=outcome, exit_reason="recommendation",
            now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)
