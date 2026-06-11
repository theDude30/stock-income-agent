import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def build_cron_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week="mon-fri",
        hour=17,
        minute=15,
        timezone="America/New_York",
    )


def build_learner_cron_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week="fri",
        hour=17,
        minute=30,
        timezone="America/New_York",
    )


class PipelineScheduler:
    def __init__(self, job_callable: Callable, learner_callable: Callable | None = None) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job_callable = job_callable
        self._learner_callable = learner_callable
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            func=self._job_callable,
            trigger=build_cron_trigger(),
            id="daily_pipeline",
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=3600,
        )
        if self._learner_callable is not None:
            self._scheduler.add_job(
                func=self._learner_callable,
                trigger=build_learner_cron_trigger(),
                id="weekly_learner",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=3600,
            )
        self._scheduler.start()
        self._started = True
        logger.info("pipeline scheduler started (weekdays 17:15; learner Fridays 17:30 ET)")

    def stop(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("pipeline scheduler stopped")
