"""Tests for Layer 2: messages compaction."""

import importlib
import json
from pathlib import Path
from typing import Any

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse

pytest = importlib.import_module("pytest")


class DummyProvider(LLMProvider):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress: Any = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy"


def _build_messages_with_tool_pairs(n_pairs: int) -> list[dict[str, Any]]:
    """构造包含 n_pairs 个 assistant+tool 成对消息的 messages 列表。"""
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": "test system"},
        {"role": "user", "content": "test request"},
    ]
    for i in range(n_pairs):
        tc_id = f"tc-{i}"
        msgs.append(
            {
                "role": "assistant",
                "content": f"step {i}",
                "tool_calls": [
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": "exec", "arguments": "{}"},
                    }
                ],
            }
        )
        msgs.append(
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "name": "exec",
                "content": "x" * 200,
            }
        )
    return msgs


def _make_loop(tmp_path: Path) -> Any:
    from bao.agent.loop import AgentLoop

    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        model="dummy",
    )
    loop._ctx_mgmt = "auto"
    loop._compact_keep_blocks = 2
    return loop


def test_compact_messages_preserves_tool_call_pairs(tmp_path: Path) -> None:
    """compaction 后每个 tool message 的 tool_call_id 都能在 assistant(tool_calls) 中找到。"""
    loop = _make_loop(tmp_path)

    initial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "req"},
    ]
    messages = _build_messages_with_tool_pairs(10)

    compacted = loop._compact_messages(messages, initial, "some state", None)

    # 收集所有 assistant tool_call ids
    assistant_tc_ids: set[str] = set()
    for m in compacted:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                assistant_tc_ids.add(tc["id"])

    # 验证每个 tool message 的 tool_call_id 都有对应的 assistant
    for m in compacted:
        if m.get("role") == "tool":
            assert m["tool_call_id"] in assistant_tc_ids, (
                f"tool_call_id {m['tool_call_id']} has no matching assistant message"
            )


def test_compact_messages_reduces_size(tmp_path: Path) -> None:
    """compaction 后 messages bytes 估算显著下降（≥30%）。"""
    loop = _make_loop(tmp_path)

    initial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "req"},
    ]
    messages = _build_messages_with_tool_pairs(20)

    before = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
    compacted = loop._compact_messages(messages, initial, None, None)
    after = len(json.dumps(compacted, ensure_ascii=False).encode("utf-8"))

    assert after < before * 0.7, f"Expected ≥30% reduction but before={before} after={after}"


def test_short_task_no_compaction(tmp_path: Path) -> None:
    """短任务（bytes 远小于阈值）不触发 compaction。"""
    loop = _make_loop(tmp_path)
    loop._compact_bytes = 999_999_999  # 极大阈值

    msgs = _build_messages_with_tool_pairs(2)
    _bytes = len(json.dumps(msgs, ensure_ascii=False).encode("utf-8"))
    assert _bytes < loop._compact_bytes, "Short task should not exceed compact threshold"


def test_compact_messages_keeps_correct_block_count(tmp_path: Path) -> None:
    """compaction 后保留的 tool block 数量等于 _compact_keep_blocks。"""
    loop = _make_loop(tmp_path)
    loop._compact_keep_blocks = 3

    initial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "req"},
    ]
    messages = _build_messages_with_tool_pairs(10)

    compacted = loop._compact_messages(messages, initial, None, None)

    # 统计 compacted 中 assistant(tool_calls) 的数量
    block_count = sum(1 for m in compacted if m.get("role") == "assistant" and m.get("tool_calls"))
    assert block_count == 3


def test_compact_messages_includes_state_note(tmp_path: Path) -> None:
    """compaction 时 state_note 被附加到第一个 user message。"""
    loop = _make_loop(tmp_path)

    initial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "original request"},
    ]
    messages = _build_messages_with_tool_pairs(6)
    state_text = "some previous state"

    compacted = loop._compact_messages(messages, initial, state_text, None)

    user_msgs = [m for m in compacted if m.get("role") == "user"]
    assert len(user_msgs) >= 1
    assert state_text in user_msgs[0]["content"]
    assert "Compacted context" in user_msgs[0]["content"]


@pytest.mark.asyncio
async def test_run_agent_loop_triggers_layer2_compaction_when_over_budget(
    tmp_path: Path, monkeypatch
) -> None:
    loop = _make_loop(tmp_path)
    loop._compact_bytes = 1
    called = {"hit": False}

    original = loop._compact_messages

    def _spy_compact(
        messages: list[dict[str, Any]],
        initial_messages: list[dict[str, Any]],
        last_state_text: str | None,
        artifact_store: Any,
    ) -> list[dict[str, Any]]:
        called["hit"] = True
        return original(messages, initial_messages, last_state_text, artifact_store)

    monkeypatch.setattr(loop, "_compact_messages", _spy_compact)

    initial = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "req"},
        *_build_messages_with_tool_pairs(8)[2:],
    ]

    await loop._run_agent_loop(initial, artifact_session_key="gateway:c")
    assert called["hit"] is True
