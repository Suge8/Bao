from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from bao.agent.loop import AgentLoop
from bao.bus.events import ControlEvent, InboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tests._provider_request_testkit import request_messages, request_tools

DEFAULT_MESSAGES = [
    {"role": "system", "content": "test"},
    {"role": "user", "content": "call tools"},
]


@dataclass(slots=True, frozen=True)
class LoopSpec:
    provider: LLMProvider
    max_iterations: int = 2
    bus: MessageBus | None = None


@dataclass(slots=True, frozen=True)
class FakeLoopResult:
    content: str | None
    progress_text: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)


class ToolObservabilityProvider(LLMProvider):
    def __init__(self, with_tool_calls: bool):
        super().__init__(api_key=None, api_base=None)
        self._with_tool_calls = with_tool_calls
        self._calls = 0

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        _ = request_tools(request)
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


class PlannedProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse], capture_tools: bool = False):
        super().__init__(api_key=None, api_base=None)
        self._responses = list(responses)
        self.captured_tools: list[list[dict[str, Any]] | None] = []
        self._capture_tools = capture_tools

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        tools = request_tools(request)
        if self._capture_tools:
            self.captured_tools.append(tools)
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def build_loop(tmp_path: Path, spec: LoopSpec) -> AgentLoop:
    return AgentLoop(
        bus=spec.bus or MessageBus(),
        provider=spec.provider,
        workspace=tmp_path,
        max_iterations=spec.max_iterations,
    )


def prepare_workspace(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready", encoding="utf-8")


def run_default_turn(loop: AgentLoop, content: str) -> tuple[Any, ...]:
    return asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                DEFAULT_MESSAGES[0],
                {"role": "user", "content": content},
            ]
        )
    )


def imessage_message() -> InboundMessage:
    return InboundMessage(
        channel="imessage",
        sender_id="u1",
        chat_id="c1",
        content="帮我处理一下",
    )


def system_message(content: str) -> InboundMessage:
    return InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="imessage:+86100",
        content=content,
        metadata={"session_key": "imessage:+86100"},
    )


def error_control_event() -> ControlEvent:
    return ControlEvent(
        kind="subagent_result",
        session_key="imessage:+86100",
        origin_channel="imessage",
        origin_chat_id="+86100",
        metadata={"session_key": "imessage:+86100"},
        payload={
            "type": "subagent_result",
            "task_id": "task-2",
            "label": "repair",
            "task": "处理失败路径",
            "status": "error",
            "result": "tool failed",
        },
    )


def tool_call_response(name: str, arguments: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        content="tools",
        tool_calls=[ToolCallRequest(id="tc-1", name=name, arguments=arguments)],
        finish_reason="tool_calls",
    )


def install_fake_run(loop: AgentLoop, result: FakeLoopResult) -> None:
    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages
        options = kwargs.get("options")
        on_progress = kwargs.get("on_progress")
        if on_progress is None and options is not None:
            on_progress = getattr(options, "on_progress", None)
        if result.progress_text and on_progress is not None:
            await cast(Any, on_progress)(result.progress_text)
        return (
            result.content,
            [],
            [],
            0,
            result.attachments,
            False,
            False,
            [],
            [],
        )

    setattr(loop, "_run_agent_loop", _fake_run_agent_loop)
