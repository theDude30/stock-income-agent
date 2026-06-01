import pytest


def test_scheduler_job_has_weekday_17_15_eastern_cron():
    from app.pipeline.scheduler import build_cron_trigger

    trigger = build_cron_trigger()
    # APScheduler 3.x: str() omits timezone but repr() includes it.
    # Use repr() so all four assertions can be checked in one pass.
    s = repr(trigger)
    assert "day_of_week='mon-fri'" in s
    assert "hour='17'" in s
    assert "minute='15'" in s
    assert "America/New_York" in s


@pytest.mark.asyncio(loop_scope="session")
async def test_scheduler_start_and_stop_idempotent():
    from app.pipeline.scheduler import PipelineScheduler

    sched = PipelineScheduler(job_callable=lambda: None)
    sched.start()
    sched.start()  # idempotent
    sched.stop()
    sched.stop()  # idempotent
