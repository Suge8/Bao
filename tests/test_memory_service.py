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
    def submit(self, coro: Coroutine[Any, Any, Any]) -> _FakeFuture:
        coro.close()
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


def test_selected_memory_fact_read_model_tracks_selection_and_fallback() -> None:
    service = MemoryService(_FakeRunner())
    detail = {
        "category": "project",
        "content": "Fact A\nFact B",
        "facts": [
            {"key": "fact-a", "content": "Fact A"},
            {"key": "fact-b", "content": "Fact B"},
        ],
    }

    service._apply_selected_memory_category("project", detail)
    assert service.selectedMemoryFactKey == "fact-a"
    assert service.selectedMemoryFact["content"] == "Fact A"

    service.selectMemoryFact("fact-b")
    assert service.selectedMemoryFactKey == "fact-b"
    assert service.selectedMemoryFact["content"] == "Fact B"

    service._apply_selected_memory_category(
        "project",
        {
            **detail,
            "content": "Fact B",
            "facts": [{"key": "fact-b", "content": "Fact B"}],
        },
        "fact-a",
    )
    assert service.selectedMemoryFactKey == "fact-b"
    assert service.selectedMemoryFact["content"] == "Fact B"
