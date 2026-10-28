"""Background worker: drains the outbox, fires reminders, re-verifies listings, applies retention.

Crash-safe: all state lives in the database; on restart the worker resumes from unprocessed events.
Run with: python -m app.worker
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time

from app.db import get_sessionmaker
from app.logging_setup import configure_logging
from app.services import tasks

log = logging.getLogger("jobpilot.worker")


async def run_forever(poll_seconds: float = 2.0, periodic_seconds: float = 60.0) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    last_periodic = 0.0
    log.info("worker started")
    while not stop.is_set():
        try:
            async with get_sessionmaker()() as session:
                await tasks.process_outbox(session)
                if time.monotonic() - last_periodic > periodic_seconds:
                    await tasks.due_reminders(session)
                    await tasks.reverify_stale(session)
                    await tasks.apply_retention(session)
                    last_periodic = time.monotonic()
                await session.commit()
        except Exception:
            log.exception("worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
    log.info("worker stopped")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_forever())
