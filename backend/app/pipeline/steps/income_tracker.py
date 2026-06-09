import logging
from datetime import date
from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_assignment_gain,
    compute_capital_pnl,
    compute_covered_call_return_pct,
    compute_total_return_pct,
    is_call_itm,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class IncomeTrackerStep(Step):
    name = "income_tracker"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        ok, failures = 0, {}
        today = ctx.now().date()

        # 1. Dividend tracking for open stock positions
        stock_positions = await ctx.repo.list_open_positions(kind="stock")
        for pos in stock_positions:
            try:
                await self._track_dividends(ctx, pos, today)
                ok += 1
            except Exception as exc:
                logger.warning("income_tracker: dividend %s: %s", pos.ticker, exc)
                failures[pos.ticker] = str(exc)

        # 2. Call expiry / assignment
        expiring_calls = await ctx.repo.open_calls_expiring_on(today)
        for pos in expiring_calls:
            try:
                await self._settle_call(ctx, pos, today)
                ok += 1
            except Exception as exc:
                logger.warning("income_tracker: call settle %s: %s", pos.ticker, exc)
                failures[pos.ticker] = str(exc)

        return StepResult(ok_count=ok, per_ticker_failures=failures)

    async def _track_dividends(self, ctx: StepContext, pos, today: date) -> None:
        dividends = await ctx.repo.dividends_since(pos.ticker, pos.opened_at.date())
        for div in dividends:
            if div.ex_date > today:
                continue
            amount = div.amount_per_share * pos.shares
            await ctx.repo.insert_income_event(
                ticker=pos.ticker, type_="dividend",
                amount=amount, event_date=div.ex_date,
                source_position_id=pos.id,
                source_recommendation_id=None,
                now=ctx.now(),
            )

    async def _settle_call(self, ctx: StepContext, pos, today: date) -> None:
        close = await ctx.repo.latest_close(pos.ticker)
        if close is None:
            raise ValueError(f"no close price for {pos.ticker}")
        close_dec = Decimal(str(close))

        if is_call_itm(pos.strike, close_dec):
            await self._handle_assignment(ctx, pos, close_dec, today)
        else:
            await self._handle_otm_expiry(ctx, pos, today)

    async def _handle_otm_expiry(self, ctx: StepContext, pos, today: date) -> None:
        # Call expired worthless — premium already booked at open
        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=pos.ticker, side="expire",
            shares_or_contracts=pos.shares, price=Decimal("0"),
            reason="expiration", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "expired", ctx.now())

        # Find underlying stock position for cost basis (best effort)
        stock_positions = await ctx.repo.list_open_positions(ticker=pos.ticker, kind="stock")
        premium_total = pos.avg_entry_price * 100
        if stock_positions:
            sp = stock_positions[0]
            cost_basis = sp.avg_entry_price * sp.shares
            total_return_pct = compute_covered_call_return_pct(premium_total, cost_basis)
        else:
            logger.warning(
                "income_tracker: OTM expiry for %s (position %d) has no open stock position — "
                "feedback will show total_return_pct=0",
                pos.ticker, pos.id,
            )
            total_return_pct = Decimal("0")

        await ctx.repo.insert_feedback(
            rec_id=pos.recommendation_id, position_id=pos.id,
            entry_price=pos.avg_entry_price, exit_price=Decimal("0"),
            capital_pnl=Decimal("0"), dividends_received=Decimal("0"),
            premiums_collected=premium_total,
            total_return_pct=total_return_pct,
            held_days=(today - pos.opened_at.date()).days,
            outcome="win",  # premium kept, shares retained
            exit_reason="expiration", now=ctx.now(),
        )

    async def _handle_assignment(self, ctx: StepContext, pos, close_dec: Decimal, today: date) -> None:
        # Call ITM — shares assigned at strike
        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=pos.ticker, side="assign",
            shares_or_contracts=pos.shares * 100,
            price=pos.strike, reason="assignment", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "assigned", ctx.now())

        stock_positions = await ctx.repo.list_open_positions(ticker=pos.ticker, kind="stock")
        if stock_positions:
            sp = stock_positions[0]
            await ctx.repo.close_position(sp.id, "assigned", ctx.now())

            assignment_gain = compute_assignment_gain(pos.strike, sp.avg_entry_price, sp.shares)
            if assignment_gain > 0:
                await ctx.repo.insert_income_event(
                    ticker=pos.ticker, type_="assignment_gain",
                    amount=assignment_gain, event_date=today,
                    source_position_id=sp.id, source_recommendation_id=None,
                    now=ctx.now(),
                )

            capital_pnl = compute_capital_pnl(sp.avg_entry_price, pos.strike, sp.shares)
            premium_total = pos.avg_entry_price * 100
            cost_basis = sp.avg_entry_price * sp.shares
            total_return_pct = compute_total_return_pct(capital_pnl, Decimal(0), premium_total, cost_basis)
            outcome = classify_outcome(total_return_pct)

            await ctx.repo.insert_feedback(
                rec_id=sp.recommendation_id, position_id=sp.id,
                entry_price=sp.avg_entry_price, exit_price=pos.strike,
                capital_pnl=capital_pnl, dividends_received=Decimal(0),
                premiums_collected=premium_total,
                total_return_pct=total_return_pct,
                held_days=(today - sp.opened_at.date()).days,
                outcome=outcome, exit_reason="assignment", now=ctx.now(),
            )
        else:
            logger.warning(
                "income_tracker: ITM assignment for %s (call pos %d) has no open stock position — "
                "no feedback written",
                pos.ticker, pos.id,
            )
