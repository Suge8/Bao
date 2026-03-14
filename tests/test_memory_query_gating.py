from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from bao.agent.loop import AgentLoop
from bao.agent.memory import MemoryStore
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse


class _FinalOnlyProvider(LLMProvider):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="收到。", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def _build_store() -> MemoryStore:
    store = MemoryStore.__new__(MemoryStore)
    store._store_lock = threading.RLock()
    store._embed_fn = None
    store._vec_tbl = None
    return store


class _CountingSearch:
    def __init__(self, table: "_CountingTable") -> None:
        self._table = table
        self._where: str | None = None
        self._limit: int | None = None

    def where(self, expr: str):
        self._where = expr
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def to_list(self) -> list[dict[str, object]]:
        rows = self._table.rows
        if self._where == "type = 'long_term'":
            rows = [row for row in rows if row.get("type") == "long_term"]
        if self._limit is not None:
            rows = rows[: self._limit]
        return [dict(row) for row in rows]


class _CountingTable:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = [dict(row) for row in rows]
        self.search_calls = 0

    def search(self, *_args, **_kwargs):
        self.search_calls += 1
        return _CountingSearch(self)

    def add(self, rows: list[dict[str, object]]) -> None:
        for row in rows:
            self.rows.append(dict(row))

    def delete(self, where: str) -> None:
        if where == "type = 'long_term' AND category = 'project'":
            self.rows = [
                row
                for row in self.rows
                if not (row.get("type") == "long_term" and row.get("category") == "project")
            ]


def test_should_skip_retrieval_for_low_information_query() -> None:
    store = _build_store()
    assert store.should_skip_retrieval("好的") is True
    assert store.should_skip_retrieval("Thanks!") is True
    assert store.should_skip_retrieval("帮我查 AI 新闻") is False


def test_get_relevant_memory_context_returns_empty_when_query_is_weak_or_unmatched() -> None:
    store = _build_store()
    store._tbl = _CountingTable(
        [
            {"type": "long_term", "category": "project", "content": "项目里有缓存策略"},
            {"type": "long_term", "category": "general", "content": "偏好是简洁回复"},
        ]
    )

    assert store.get_relevant_memory_context("好的", max_chars=200) == ""
    assert store.get_relevant_memory_context("完全不相关的问题", max_chars=200) == ""


def test_get_memory_context_reads_long_term_rows_once() -> None:
    store = _build_store()
    store._tbl = _CountingTable(
        [
            {"type": "long_term", "category": "project", "content": "项目里有缓存策略"},
            {"type": "long_term", "category": "general", "content": "偏好简洁回复"},
        ]
    )

    text = store.get_memory_context(max_chars=200)

    assert "项目里有缓存策略" in text
    assert "偏好简洁回复" in text
    assert store._tbl.search_calls == 1


def test_get_relevant_memory_context_reads_long_term_rows_once() -> None:
    store = _build_store()
    store._tbl = _CountingTable(
        [
            {"type": "long_term", "category": "project", "content": "项目里有缓存策略"},
            {"type": "long_term", "category": "general", "content": "偏好简洁回复"},
        ]
    )

    text = store.get_relevant_memory_context("缓存策略", max_chars=200)

    assert "项目里有缓存策略" in text
    assert "偏好简洁回复" not in text
    assert store._tbl.search_calls == 1


def test_long_term_write_invalidates_retrieval_index() -> None:
    store = _build_store()
    store._tbl = _CountingTable(
        [
            {"type": "long_term", "category": "project", "content": "旧的缓存策略"},
            {"type": "long_term", "category": "general", "content": "偏好简洁回复"},
        ]
    )

    first = store.get_relevant_memory_context("缓存策略", max_chars=200)
    store.write_long_term("新的缓存策略", "project")
    second = store.get_relevant_memory_context("新的缓存策略", max_chars=200)

    assert "旧的缓存策略" in first
    assert "新的缓存策略" in second
    assert store._tbl.search_calls == 3


def test_process_message_skips_memory_search_for_low_information_turn(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready\n", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready\n", encoding="utf-8")

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FinalOnlyProvider(api_key=None, api_base=None),
        workspace=tmp_path,
        max_iterations=2,
    )
    loop._tool_exposure_mode = "off"

    loop.context.memory.should_skip_retrieval = lambda _query: True  # type: ignore[method-assign]
    loop.context.memory.get_relevant_memory_context = lambda *_args, **_kwargs: ""  # type: ignore[method-assign]

    def _fail_search(_query: str, limit: int = 5):
        del limit
        raise AssertionError("search_memory should be skipped for low-information turns")

    def _fail_experience(_query: str, limit: int = 3):
        del limit
        raise AssertionError("search_experience should be skipped for low-information turns")

    loop.context.memory.search_memory = _fail_search  # type: ignore[method-assign]
    loop.context.memory.search_experience = _fail_experience  # type: ignore[method-assign]

    msg = InboundMessage(
        channel="desktop",
        sender_id="tester",
        chat_id="local",
        content="好的",
    )

    out = asyncio.run(loop._process_message(msg))
    assert out is not None
    assert out.content == "收到。"
