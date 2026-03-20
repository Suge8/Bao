from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from tests._tool_observability_testkit import (
    LoopSpec,
    ToolObservabilityProvider,
    build_loop,
    error_control_event,
    prepare_workspace,
    system_message,
)


def test_process_system_message_localizes_blank_final_fallback(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))

    session = loop.sessions.get_or_create("imessage:+86100")
    session.metadata["_session_lang"] = "zh"
    loop.sessions.save(session)

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return "", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    out = asyncio.run(loop._process_system_message(system_message("")))
    assert out is not None
    assert out.content == "后台任务已完成。"
    assert "system_event" not in out.metadata

    persisted = loop.sessions.get_or_create("imessage:+86100").messages
    assert len(persisted) == 1
    assert persisted[0]["role"] == "assistant"
    assert persisted[0]["content"] == "后台任务已完成。"
    assert persisted[0].get("_source") is None


def test_process_system_message_error_event_uses_same_summary_path(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))
    captured_messages: list[list[dict[str, Any]]] = []

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        captured_messages.append(initial_messages)
        del kwargs
        return "任务失败，请稍后再试。", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    out = asyncio.run(loop._process_control_event(error_control_event()))
    assert out is not None
    assert out.content == "任务失败，请稍后再试。"
    assert "system_event" not in out.metadata
    assert captured_messages

    user_contents = [item.get("content", "") for item in captured_messages[0] if item.get("role") == "user"]
    assert any("[Background task failed]" in content for content in user_contents)

    persisted = loop.sessions.get_or_create("imessage:+86100").messages
    assert len(persisted) == 1
    assert persisted[0]["role"] == "assistant"
    assert persisted[0]["content"] == "任务失败，请稍后再试。"
    assert persisted[0].get("_source") is None


def test_process_system_message_uses_content_directly(tmp_path: Path) -> None:
    prepare_workspace(tmp_path)
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=False)))
    captured_messages: list[list[dict[str, Any]]] = []

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        captured_messages.append(initial_messages)
        del kwargs
        return "按旧 system 内容处理。", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    out = asyncio.run(loop._process_system_message(system_message("legacy system payload")))
    assert out is not None
    assert out.content == "按旧 system 内容处理。"
    assert "system_event" not in out.metadata
    assert captured_messages

    user_contents = [item.get("content", "") for item in captured_messages[0] if item.get("role") == "user"]
    assert "legacy system payload" in user_contents
