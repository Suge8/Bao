from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from bao.agent.loop import AgentLoop
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
