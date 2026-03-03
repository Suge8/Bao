from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from bao.agent.loop import AgentLoop
from bao.agent.tools.message import MessageTool
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class ToolObservabilityProvider(LLMProvider):
    def __init__(self, with_tool_calls: bool):
        super().__init__(api_key=None, api_base=None)
        self._with_tool_calls = with_tool_calls
        self._calls = 0

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
        if self._with_tool_calls and self._calls == 0:
            self._calls += 1
            return LLMResponse(
                content="tools",
                tool_calls=[
                    ToolCallRequest(id="tc-1", name="missing_tool", arguments={}),
                    ToolCallRequest(id="tc-2", name="read_file", arguments={}),
                ],
                finish_reason="tool_calls",
            )
        self._calls += 1
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_run_agent_loop_collects_tool_observability(tmp_path: Path) -> None:
    provider = ToolObservabilityProvider(with_tool_calls=True)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=4,
    )
    loop._tool_exposure_mode = "off"

    final_content, tools_used, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "call tools"},
            ]
        )
    )

    assert final_content == "done"
    assert tools_used == ["missing_tool", "read_file"]

    obs = loop._last_tool_observability
    assert obs["schema_samples"] >= 1
    assert obs["schema_tool_count_last"] > 0
    assert obs["schema_bytes_last"] > 0
    assert obs["tool_calls_total"] == 2
    assert obs["tool_calls_error"] == 2
    assert obs["invalid_parameter_errors"] == 1
    assert obs["tool_not_found_errors"] == 1
    assert obs["retry_attempts_proxy"] == 1
    assert obs["tool_selection_hit_rate"] == 0.0
    assert obs["parameter_fill_success_rate"] == 0.5
    assert obs["retry_rate_proxy"] == 0.5


def test_interrupted_tool_call_not_counted_as_ok(tmp_path: Path) -> None:
    class InterruptedToolProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__(api_key=None, api_base=None)
            self._calls = 0

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
            if self._calls == 0:
                self._calls += 1
                return LLMResponse(
                    content="tools",
                    tool_calls=[
                        ToolCallRequest(id="tc-cancel", name="read_file", arguments={"path": "x"})
                    ],
                    finish_reason="tool_calls",
                )
            self._calls += 1
            return LLMResponse(content="done", finish_reason="stop")

        def get_default_model(self) -> str:
            return "dummy/model"

    provider = InterruptedToolProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=3,
    )
    loop._tool_exposure_mode = "off"

    async def _fake_execute(name: str, params: dict[str, Any]) -> str:
        del name, params
        return "Cancelled by soft interrupt."

    loop.tools.execute = _fake_execute

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "call tools"},
            ]
        )
    )

    assert final_content == "done"
    obs = loop._last_tool_observability
    assert obs["tool_calls_total"] == 1
    assert obs["interrupted_tool_calls"] == 1
    assert obs["tool_calls_error"] == 0
    assert obs["tool_calls_ok"] == 0


def test_process_message_persists_tool_observability_in_session_metadata(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")

    provider = ToolObservabilityProvider(with_tool_calls=False)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content="hello",
    )
    out = asyncio.run(loop._process_message(msg))

    assert out is not None
    assert isinstance(out.metadata.get("_tool_observability"), dict)

    session = loop.sessions.get_or_create("telegram:c1")
    last_entry = session.metadata.get("_tool_observability_last")
    recent_entries = session.metadata.get("_tool_observability_recent")
    assert isinstance(last_entry, dict)
    assert isinstance(recent_entries, list)
    assert len(recent_entries) == 1
    assert last_entry["schema_tool_count_last"] > 0


def test_process_message_localizes_empty_final_fallback(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")

    provider = ToolObservabilityProvider(with_tool_calls=False)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return None, [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    msg = InboundMessage(
        channel="imessage",
        sender_id="u1",
        chat_id="c1",
        content="帮我处理一下",
    )

    out = asyncio.run(loop._process_message(msg))
    assert out is not None
    assert out.content == "处理完成。"


def test_process_message_localizes_blank_final_fallback(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")

    provider = ToolObservabilityProvider(with_tool_calls=False)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return "   ", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    msg = InboundMessage(
        channel="imessage",
        sender_id="u1",
        chat_id="c1",
        content="帮我处理一下",
    )

    out = asyncio.run(loop._process_message(msg))
    assert out is not None
    assert out.content == "处理完成。"


def test_process_system_message_localizes_blank_final_fallback(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")

    provider = ToolObservabilityProvider(with_tool_calls=False)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    session = loop.sessions.get_or_create("imessage:+86100")
    session.metadata["_session_lang"] = "zh"
    loop.sessions.save(session)

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return "", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="imessage:+86100",
        content="done",
        metadata={"session_key": "imessage:+86100"},
    )

    out = asyncio.run(loop._process_system_message(msg))
    assert out is not None
    assert out.content == "后台任务已完成。"


def test_run_agent_loop_blocks_tool_not_exposed_for_turn(tmp_path: Path) -> None:
    class NonExposedToolProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__(api_key=None, api_base=None)
            self._calls = 0

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
            del messages, model, max_tokens, temperature, on_progress, kwargs
            if self._calls == 0:
                self._calls += 1
                return LLMResponse(
                    content="tools",
                    tool_calls=[
                        ToolCallRequest(id="tc-1", name="read_file", arguments={"path": "x"})
                    ],
                    finish_reason="tool_calls",
                )
            self._calls += 1
            return LLMResponse(content="done", finish_reason="stop")

        def get_default_model(self) -> str:
            return "dummy/model"

    provider = NonExposedToolProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=3,
    )
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_bundles = {"core"}

    executed: list[str] = []

    async def _fake_execute(name: str, params: dict[str, Any]) -> str:
        executed.append(name)
        del params
        return "ok"

    loop.tools.execute = _fake_execute

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "你好"},
            ]
        )
    )

    assert final_content == "done"
    assert executed == []
    obs = loop._last_tool_observability
    assert obs["tool_not_found_errors"] == 1


def test_run_agent_loop_force_final_never_executes_tool_calls(tmp_path: Path) -> None:
    class ForceFinalToolProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__(api_key=None, api_base=None)
            self._calls = 0
            self.tools_payloads: list[list[dict[str, Any]] | None] = []

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
            del messages, model, max_tokens, temperature, on_progress, kwargs
            self.tools_payloads.append(tools)
            if self._calls == 0:
                self._calls += 1
                return LLMResponse(
                    content="tools",
                    tool_calls=[
                        ToolCallRequest(id="tc-1", name="exec", arguments={"command": "echo x"})
                    ],
                    finish_reason="tool_calls",
                )
            self._calls += 1
            return LLMResponse(content="done", finish_reason="stop")

        def get_default_model(self) -> str:
            return "dummy/model"

    provider = ForceFinalToolProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=3,
    )

    executed: list[str] = []

    async def _fake_execute(name: str, params: dict[str, Any]) -> str:
        executed.append(name)
        del params
        return "ok"

    loop.tools.execute = _fake_execute

    async def _force_final_precheck(**kwargs: Any):
        state = kwargs["state"]
        state.force_final_response = True
        return kwargs["messages"]

    loop._apply_pre_iteration_checks = _force_final_precheck

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "call tools"},
            ]
        )
    )

    assert final_content == "done"
    assert executed == []
    assert provider.tools_payloads
    assert provider.tools_payloads[0] == []


def test_process_message_suppression_emits_progress_clear(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")

    provider = ToolObservabilityProvider(with_tool_calls=False)
    bus = MessageBus()
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages
        on_progress = kwargs.get("on_progress")
        if on_progress is not None:
            await cast(Any, on_progress)(
                '运行这条命令静音：\nosascript -e "set volume output muted true"'
            )
        tool = loop.tools.get("message")
        if isinstance(tool, MessageTool):
            tool._sent_in_turn = True
        return "最终结果", [], [], 0, [], False, False, []

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)

    msg = InboundMessage(
        channel="imessage",
        sender_id="u1",
        chat_id="c1",
        content="帮我静音",
    )

    out = asyncio.run(loop._process_message(msg))
    assert out is None

    first = asyncio.run(asyncio.wait_for(bus.consume_outbound(), timeout=1.0))
    second = asyncio.run(asyncio.wait_for(bus.consume_outbound(), timeout=1.0))
    assert first.metadata.get("_progress") is True
    assert second.metadata.get("_progress") is True
    assert second.metadata.get("_progress_clear") is True
    assert second.content == ""
