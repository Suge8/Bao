"""AsyncioRunner — runs an asyncio event loop in a dedicated background thread.

Usage:
    runner = AsyncioRunner()
    runner.start()
    future = runner.submit(some_coroutine())
    result = future.result(timeout=5)
    runner.shutdown(grace_s=3.0)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AsyncioRunner:
    """Runs an asyncio event loop in a dedicated daemon thread.

    All coroutines submitted via :meth:`submit` are scheduled on that loop,
    keeping the Qt main thread free of any asyncio blocking.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background asyncio thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped = False
        self._started.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="asyncio-runner")
        self._thread.start()
        self._started.wait(timeout=5)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.set_exception_handler(self._handle_exception)
        self._started.set()
        try:
            self._loop.run_forever()
        finally:
            # Drain remaining tasks
            pending = asyncio.all_tasks(self._loop)
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    def shutdown(self, grace_s: float = 3.0) -> None:
        """Stop the event loop and wait for the thread to finish."""
        if self._loop is None or self._stopped:
            return
        self._stopped = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=grace_s)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Schedule *coro* on the background loop; return a Future."""
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError("AsyncioRunner is not running — call start() first")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_exception(self, loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exc = context.get("exception")
        msg = context.get("message", "unknown asyncio error")
        if exc:
            logger.error("Unhandled asyncio exception: %s", msg, exc_info=exc)
        else:
            logger.error("Asyncio error: %s", msg)
