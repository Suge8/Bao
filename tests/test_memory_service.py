from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

import pytest

pytest.importorskip("PySide6")

from app.backend.memory import MemoryService


class _FakeFuture:
    def add_done_callback(self, _callback: Any) -> None:
        return None


class _FakeRunner:
    def submit(self, _coro: Coroutine[Any, Any, Any]) -> _FakeFuture:
        return _FakeFuture()


async def _noop() -> None:
    return None


def test_submit_task_rejects_overlapping_blocking_mutations() -> None:
    service = MemoryService(_FakeRunner())
    events: list[tuple[str, bool]] = []
    service.operationFinished.connect(lambda message, ok: events.append((message, ok)))

    service._set_blocking_busy(True)
    service._submit_task("save_memory", _noop())

    assert events == [(MemoryService._MUTATION_BUSY_MESSAGE, False)]


def test_submit_task_allows_non_blocking_refresh_while_busy() -> None:
    service = MemoryService(_FakeRunner())
    service._set_blocking_busy(True)

    service._submit_task("load_memory", _noop())

    assert service.blockingBusy is True
