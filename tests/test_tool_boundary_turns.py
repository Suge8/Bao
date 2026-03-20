from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from bao.agent.loop import AgentLoop
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tests._provider_request_testkit import request_messages


class _ToolBoundaryProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)
        self._calls = 0

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        if self._calls == 0:
            self._calls += 1
            return LLMResponse(
                content="我现在去看看。",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-1",
                        name="web_search",
                        arguments={"query": "latest ai news"},
                    )
                ],
                finish_reason="tool_calls",
            )
        self._calls += 1
        return LLMResponse(content="整理好了，这是结果。", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_process_message_persists_visible_pre_tool_turn_but_hides_it_from_prompt_history(
    tmp_path: Path,
) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("ready\n", encoding="utf-8")
    (tmp_path / "PERSONA.md").write_text("ready\n", encoding="utf-8")
    provider = _ToolBoundaryProvider()
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, max_iterations=4)
    loop._tool_exposure_mode = "off"

    async def _fake_execute(name: str, params: dict[str, Any], **_kwargs: Any) -> str:
        del name, params
        return "tool ok"

    loop.tools.execute = _fake_execute

    msg = InboundMessage(
        channel="desktop",
        sender_id="tester",
        chat_id="local",
        content="帮我查一下 AI 新闻",
    )

    out = asyncio.run(loop._process_message(msg))
    assert out is not None
    assert out.content == "整理好了，这是结果。"

    session = loop.sessions.get_or_create("desktop:local")
    display = session.get_display_history()
    assert [entry["content"] for entry in display] == [
        "帮我查一下 AI 新闻",
        "我现在去看看。",
        "🔎 搜索网页: latest ai news",
        "整理好了，这是结果。",
    ]
    assert display[1]["_source"] == "assistant-progress"
    assert display[2]["_source"] == "assistant-progress"

    prompt_history = session.get_history()
    assert [entry["content"] for entry in prompt_history] == [
        "帮我查一下 AI 新闻",
        "整理好了，这是结果。",
    ]
