from datetime import date

from app.pipeline.steps.base import Step, StepContext, StepResult


class UniverseStep(Step):
    name = "universe"
    is_critical = False

    def should_run(self, ctx: StepContext) -> bool:
        now = ctx.now()
        # Run on the first weekday (Mon=0..Fri=4) of the month, or on an empty stocks table.
        if now.weekday() > 4:
            return False
        # First weekday of the month = day 1-3 (Mon Jun 1, or if Sat/Sun, first Monday is the 2nd or 3rd).
        return now.day <= 3 and now.weekday() <= 4 and self._is_first_weekday_of_month(now.date())

    def _is_first_weekday_of_month(self, d: date) -> bool:
        # The first weekday of the month is day 1 if Mon-Fri,
        # day 2 if d==2 and weekday()==0 (Sunday was day 1),
        # day 3 if d==3 and weekday()==0 (Saturday + Sunday were days 1-2).
        if d.weekday() > 4:
            return False
        for earlier_day in range(1, d.day):
            earlier = d.replace(day=earlier_day)
            if earlier.weekday() <= 4:
                return False
        return True

    async def run(self, ctx: StepContext) -> StepResult:
        stocks = list(ctx.sources.universe.fetch_sp500())
        today = ctx.now().date()
        await ctx.repo.upsert_stocks(stocks, today=today)
        return StepResult(ok_count=len(stocks))
