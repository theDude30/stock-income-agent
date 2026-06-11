import pytest

from app.pipeline.scheduler import PipelineScheduler, build_learner_cron_trigger


def test_learner_cron_trigger_is_friday_1730():
    trig = build_learner_cron_trigger()
    fields = {f.name: str(f) for f in trig.fields}
    assert fields["day_of_week"] == "fri"
    assert fields["hour"] == "17"
    assert fields["minute"] == "30"


@pytest.mark.asyncio(loop_scope="session")
async def test_scheduler_registers_two_jobs_when_learner_given():
    called = []
    sched = PipelineScheduler(job_callable=lambda: called.append("daily"),
                              learner_callable=lambda: called.append("learner"))
    sched.start()
    try:
        ids = {job.id for job in sched._scheduler.get_jobs()}
        assert {"daily_pipeline", "weekly_learner"} <= ids
    finally:
        sched.stop()


@pytest.mark.asyncio(loop_scope="session")
async def test_scheduler_single_job_when_no_learner():
    sched = PipelineScheduler(job_callable=lambda: None)
    sched.start()
    try:
        ids = {job.id for job in sched._scheduler.get_jobs()}
        assert ids == {"daily_pipeline"}
    finally:
        sched.stop()
