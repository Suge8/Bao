from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any, cast

from bao.agent.loop import AgentLoop
from bao.agent.subagent import SpawnIssue, SpawnResult, SubagentManager
from bao.agent.tools.spawn import SpawnTool
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse
from bao.session.manager import SessionManager

pytest = importlib.import_module("pytest")


class _DummyManager:
    def __init__(self, result: SpawnResult):
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "gateway",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        context_from: str | None = None,
        child_session_key: str | None = None,
    ) -> SpawnResult:
        self.calls.append(
            {
                "task": task,
                "label": label,
                "origin_channel": origin_channel,
                "origin_chat_id": origin_chat_id,
                "session_key": session_key,
                "context_from": context_from,
                "child_session_key": child_session_key,
            }
        )
        return self.result


def _spawned_result(task_id: str, *, label: str = "worker") -> SpawnResult:
    return SpawnResult.spawned(task_id=task_id, label=label, child_session_key=None)


def _parse_payload(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


class _NoopProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_spawn_tool_notifies_zh_on_success() -> None:
    sent: list[OutboundMessage] = []

    async def _publish(msg: OutboundMessage) -> None:
        sent.append(msg)

    manager = _DummyManager(_spawned_result("abc123def456"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_publish_outbound(_publish)
    tool.set_context(
        "imessage",
        "+86100",
        session_key="imessage:+86100",
        lang="zh",
        reply_metadata={
            "slack": {"thread_ts": "1710000.123", "channel_type": "channel"},
            "ignored": {"x": 1},
        },
    )

    result = asyncio.run(tool.execute(task="处理任务", label="worker"))
    payload = _parse_payload(result)
    assert payload["status"] == "spawned"
    assert payload["task"]["task_id"] == "abc123def456"
    assert len(sent) == 1
    assert sent[0].content == "已委派子代理处理中，完成后我会同步结果。"
    assert sent[0].metadata.get("session_key") == "imessage:+86100"
    spawn_meta = sent[0].metadata.get("_subagent_spawn")
    assert isinstance(spawn_meta, dict)
    assert spawn_meta["task"]["task_id"] == "abc123def456"
    assert sent[0].metadata.get("slack") == {
        "thread_ts": "1710000.123",
        "channel_type": "channel",
    }


@pytest.mark.asyncio
async def test_spawn_tool_passes_child_session_key() -> None:
    manager = _DummyManager(_spawned_result("abc123def456"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_context("desktop", "local", session_key="desktop:local::main", lang="zh")

    result = await tool.execute(
        task="continue", child_session_key="subagent:desktop:local::main::child"
    )

    payload = _parse_payload(result)
    assert payload["task"]["task_id"] == "abc123def456"
    assert manager.calls[0]["session_key"] == "desktop:local::main"
    assert manager.calls[0]["child_session_key"] == "subagent:desktop:local::main::child"


def test_spawn_tool_notifies_en_on_success() -> None:
    sent: list[OutboundMessage] = []

    async def _publish(msg: OutboundMessage) -> None:
        sent.append(msg)

    manager = _DummyManager(_spawned_result("def456abc123"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_publish_outbound(_publish)
    tool.set_context("telegram", "c1", session_key="telegram:c1", lang="en")

    result = asyncio.run(tool.execute(task="Do work", label="worker"))
    payload = _parse_payload(result)
    assert payload["task"]["task_id"] == "def456abc123"
    assert len(sent) == 1
    assert (
        sent[0].content
        == "I've delegated this to a subagent and will share the result once it's done."
    )


def test_spawn_tool_serializes_warning_without_visible_noise() -> None:
    sent: list[OutboundMessage] = []

    async def _publish(msg: OutboundMessage) -> None:
        sent.append(msg)

    manager = _DummyManager(
        SpawnResult.spawned(
            task_id="deadbeefcafe",
            label="worker",
            child_session_key=None,
            warning=SpawnIssue(code="x", message="bad"),
        )
    )
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_publish_outbound(_publish)
    tool.set_context("imessage", "+86100", session_key="imessage:+86100", lang="zh")

    result = asyncio.run(tool.execute(task="处理任务", label="worker"))
    payload = _parse_payload(result)
    assert payload["task"]["task_id"] == "deadbeefcafe"
    assert payload["warning"] == {"code": "x", "message": "bad"}
    assert len(sent) == 1
    assert sent[0].metadata["_subagent_spawn"]["task"]["task_id"] == "deadbeefcafe"


def test_spawn_tool_skips_notify_when_spawn_fails() -> None:
    sent: list[OutboundMessage] = []

    async def _publish(msg: OutboundMessage) -> None:
        sent.append(msg)

    manager = _DummyManager(
        SpawnResult.failed(code="backend_unavailable", message="backend unavailable")
    )
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_publish_outbound(_publish)
    tool.set_context("telegram", "c1", session_key="telegram:c1", lang="zh")

    result = asyncio.run(tool.execute(task="Do work", label="worker"))
    payload = _parse_payload(result)
    assert payload["status"] == "failed"
    assert payload["error"] == {"code": "backend_unavailable", "message": "backend unavailable"}
    assert sent == []


def test_spawn_tool_rejects_missing_task_with_structured_error() -> None:
    manager = _DummyManager(_spawned_result("unused"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))

    payload = _parse_payload(asyncio.run(tool.execute(task="", label="worker")))

    assert payload["status"] == "failed"
    assert payload["error"] == {"code": "task_required", "message": "task text is required"}


def test_spawn_tool_rejects_non_string_label_with_structured_error() -> None:
    manager = _DummyManager(_spawned_result("unused"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))

    payload = _parse_payload(asyncio.run(tool.execute(task="Do work", label=123)))

    assert payload["status"] == "failed"
    assert payload["error"] == {"code": "invalid_label", "message": "label must be a string"}


def test_spawn_tool_propagates_cancelled_error_from_notify() -> None:
    async def _publish(_msg: OutboundMessage) -> None:
        raise asyncio.CancelledError()

    manager = _DummyManager(_spawned_result("feedbeefcafe"))
    tool = SpawnTool(manager=cast(SubagentManager, cast(object, manager)))
    tool.set_publish_outbound(_publish)
    tool.set_context("telegram", "c1", session_key="telegram:c1", lang="en")

    async def _run() -> None:
        await tool.execute(task="Do work", label="worker")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run())


def test_loop_set_tool_context_applies_lang_to_spawn_notice(tmp_path: Path) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_NoopProvider(),
        workspace=tmp_path,
        max_iterations=1,
    )
    spawn = loop.tools.get("spawn")
    assert isinstance(spawn, SpawnTool)

    sent: list[OutboundMessage] = []

    async def _publish(msg: OutboundMessage) -> None:
        sent.append(msg)

    spawn.set_publish_outbound(_publish)
    setattr(spawn, "_manager", _DummyManager(_spawned_result("f00ba47bad99", label="w")))

    loop._set_tool_context(
        "telegram",
        "c1",
        session_key="telegram:c1",
        lang="zh",
        metadata={"slack": {"thread_ts": "1710000.999", "channel_type": "im"}},
    )
    result = asyncio.run(spawn.execute(task="Do work", label="w"))

    payload = _parse_payload(result)
    assert payload["task"]["task_id"] == "f00ba47bad99"
    assert len(sent) == 1
    assert sent[0].content == "已委派子代理处理中，完成后我会同步结果。"
    assert sent[0].metadata.get("slack") == {
        "thread_ts": "1710000.999",
        "channel_type": "im",
    }


def test_build_child_session_notes_keeps_unknown_status(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    child = sessions.get_or_create("subagent:telegram:c1::child")
    child.metadata.update(
        {
            "title": "worker",
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": "telegram:c1",
            "task_label": "worker",
        }
    )
    sessions.save(child)

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_NoopProvider(),
        workspace=tmp_path,
        max_iterations=1,
        session_manager=sessions,
    )

    notes = loop._build_child_session_notes("telegram:c1")

    assert any("status=unknown" in line for line in notes)
