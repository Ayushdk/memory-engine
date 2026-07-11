"""In-process job runner: execution, failure isolation, lifecycle."""

import asyncio

from app.jobs.job_runner import JobRunner


async def test_enqueued_job_runs():
    runner = JobRunner()
    runner.start()
    ran = []

    async def job():
        ran.append("done")

    runner.enqueue("test", job)
    await runner.drain()
    await runner.stop()
    assert ran == ["done"]


async def test_failing_job_does_not_kill_the_worker():
    runner = JobRunner()
    runner.start()
    ran = []

    async def bad():
        raise RuntimeError("boom")

    async def good():
        ran.append("survived")

    runner.enqueue("bad", bad)
    runner.enqueue("good", good)
    await runner.drain()
    await runner.stop()
    assert ran == ["survived"]


async def test_enqueue_before_start_is_dropped_not_fatal():
    JobRunner().enqueue("orphan", lambda: asyncio.sleep(0))  # must not raise


async def test_periodic_jobs_fire():
    runner = JobRunner()
    runner.start()
    ticks = []

    async def tick():
        ticks.append(1)

    runner.start_periodic("tick", 0.01, tick)
    await asyncio.sleep(0.05)
    await runner.drain()
    await runner.stop()
    assert len(ticks) >= 2
