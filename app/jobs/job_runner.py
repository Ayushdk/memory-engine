"""In-process background job runner (intelligence-layer.md §9).

One asyncio worker draining a queue of named coroutine factories — no
Redis/Celery, this is a local-first application. A failing job is logged and
dropped; it never kills the worker. `enqueue` is thread-safe because sync
FastAPI routes run in the threadpool while the worker lives on the event
loop.
"""

import asyncio
from collections.abc import Awaitable, Callable

from loguru import logger

JobFactory = Callable[[], Awaitable[None]]


class JobRunner:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, JobFactory]] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._tasks.append(self._loop.create_task(self._worker()))

    def start_periodic(self, name: str, interval_seconds: float, factory: JobFactory) -> None:
        async def ticker() -> None:
            while True:
                await asyncio.sleep(interval_seconds)
                self.enqueue(name, factory)

        assert self._loop is not None, "start() first"
        self._tasks.append(self._loop.create_task(ticker()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def enqueue(self, name: str, factory: JobFactory) -> None:
        if self._loop is None:  # runner not started (tests, degraded startup)
            logger.warning("Job {} dropped — runner not started", name)
            return
        try:
            on_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_loop = False
        if on_loop:  # direct put: a following drain() must see this job
            self._queue.put_nowait((name, factory))
        else:  # threadpool callers (sync routes)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (name, factory))

    async def _worker(self) -> None:
        while True:
            name, factory = await self._queue.get()
            try:
                await factory()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Background job {} failed", name)
            finally:
                self._queue.task_done()

    async def drain(self) -> None:
        """Wait until the queue is empty (tests and shutdown flushes)."""
        await self._queue.join()
