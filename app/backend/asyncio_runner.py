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
        self._state_lock = threading.Lock()
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background asyncio thread (idempotent)."""
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped = False
            self._loop = None
            self._started.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="asyncio-runner")
            self._thread.start()

        if not self._started.wait(timeout=5):
            raise RuntimeError("AsyncioRunner failed to start within 5 seconds")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(self._handle_exception)
        loop.call_soon(self._started.set)
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()
            self._loop = None

    async def _drain_pending_tasks(self, timeout_s: float) -> None:
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        if not pending:
            return

        done, still_pending = await asyncio.wait(
            pending,
            timeout=max(0.01, timeout_s),
            return_when=asyncio.ALL_COMPLETED,
        )
        del done
        if not still_pending:
            return

        for task in still_pending:
            task.cancel()
        await asyncio.gather(*still_pending, return_exceptions=True)

    def shutdown(self, grace_s: float = 3.0) -> None:
        """Stop the event loop and wait for the thread to finish."""
        with self._state_lock:
            loop = self._loop
            thread = self._thread
            if loop is None or self._stopped:
                return
            self._stopped = True

        timeout_s = max(0.1, grace_s)
        if loop.is_running():
            try:
                drain_future = asyncio.run_coroutine_threadsafe(
                    self._drain_pending_tasks(timeout_s * 0.8),
                    loop,
                )
                drain_future.result(timeout=timeout_s)
            except Exception:
                logger.debug("AsyncioRunner drain timed out or failed", exc_info=True)
            finally:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass

        if thread:
            thread.join(timeout=timeout_s)
            if thread.is_alive():
                logger.warning("AsyncioRunner thread did not stop within %.2fs", timeout_s)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Schedule *coro* on the background loop; return a Future."""
        if self._stopped:
            raise RuntimeError("AsyncioRunner is shutting down")
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
