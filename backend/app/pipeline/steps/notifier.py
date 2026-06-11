import logging
from datetime import timedelta

from app.analysis.alerts import (
    build_call_expiring,
    build_dividend_upcoming,
    build_monthly_summary,
    build_new_recs_summary,
    build_safety_alert,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

CALL_EXPIRY_WINDOW_DAYS = 5
DIVIDEND_LOOKAHEAD_DAYS = 7


class NotifierStep(Step):
    name = "notifier"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        now = ctx.now()
        repo = ctx.repo

        # Idempotency: clear any alerts previously generated for this run.
        await repo.delete_alerts_for_run(ctx.run_id)

        web_payloads: list[tuple[str, dict]] = []

        # 1. New recommendations created in this run
        pending = await repo.pending_recs_for_run(ctx.run_id)
        summary = build_new_recs_summary(pending)
        if summary is not None:
            web_payloads.append(("new_recommendations", summary))

        held = await repo.held_tickers()

        # 2. Dividend safety drops on held tickers
        for ticker in held:
            delta = await repo.safety_score_delta(ticker)
            if delta is None:
                continue
            current, previous = delta
            score = await repo.latest_safety_score(ticker)
            concerns = list(score.concerns) if score is not None else []
            payload = build_safety_alert(ticker, current, previous, concerns)
            if payload is not None:
                web_payloads.append(("dividend_safety_alert", payload))

        # 3. Upcoming dividends (next 7 days) for held stock positions
        end = today + timedelta(days=DIVIDEND_LOOKAHEAD_DAYS)
        for ticker in held:
            positions = await repo.list_open_positions(ticker=ticker, kind="stock")
            shares = sum((p.shares for p in positions), start=positions[0].shares * 0) if positions else None
            if shares is None:
                continue
            for div in await repo.dividends_between(ticker, today, end):
                web_payloads.append(
                    ("dividend_payment_upcoming",
                     build_dividend_upcoming(ticker, div.ex_date, div.amount_per_share, shares)))

        # 4. Calls expiring within 5 days
        for pos in await repo.calls_expiring_within(CALL_EXPIRY_WINDOW_DAYS, today):
            web_payloads.append(("call_expiring", build_call_expiring(pos, today)))

        # 5. Monthly summary on the 1st
        if today.day == 1:
            prev_month_end = today - timedelta(days=1)
            prev_month_start = prev_month_end.replace(day=1)
            income = await repo.list_income_events(from_=prev_month_start, to=prev_month_end)
            closed = await repo.list_feedback(from_=prev_month_start, to=prev_month_end)
            month_label = prev_month_start.strftime("%Y-%m")
            web_payloads.append(
                ("monthly_summary", build_monthly_summary(income, closed, month_label)))

        # Persist web alerts
        for type_, payload in web_payloads:
            await repo.insert_alert(ctx.run_id, type_, payload, "web", None, now)

        # Email digest (only when a real sender is wired and there is something to say)
        if ctx.email is not None and ctx.email.enabled and web_payloads:
            subject = f"Stock Income Agent — {len(web_payloads)} alert(s) for {today.isoformat()}"
            body = _render_digest(today, web_payloads)
            try:
                ctx.email.send(subject=subject, body=body)
                await repo.insert_alert(
                    ctx.run_id, "new_recommendations" if summary else web_payloads[0][0],
                    {"digest": True, "alert_count": len(web_payloads)}, "email", now, now)
            except Exception as e:
                logger.warning("notifier: email send failed: %s", e)

        return StepResult(ok_count=len(web_payloads))


def _render_digest(today, web_payloads: list[tuple[str, dict]]) -> str:
    lines = [f"Stock Income Agent digest for {today.isoformat()}", ""]
    for type_, payload in web_payloads:
        lines.append(f"[{type_}] {payload}")
    return "\n".join(lines)
