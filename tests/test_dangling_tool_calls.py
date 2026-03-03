from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

from bao.agent import shared
from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse


def test_patch_dangling_tool_results_is_idempotent() -> None:
    messages: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_missing",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                },
                {
                    "id": "call_existing",
                    "type": "function",
                    "function": {"name": "list_dir", "arguments": "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_existing",
            "name": "list_dir",
            "content": "ok",
        },
    ]

    inserted = shared.patch_dangling_tool_results(messages)
    assert inserted == 1

    tool_ids = [m.get("tool_call_id") for m in messages if m.get("role") == "tool"]
    assert "call_missing" in tool_ids
    assert "call_existing" in tool_ids

    snapshot = copy.deepcopy(messages)
    inserted_again = shared.patch_dangling_tool_results(messages)
    assert inserted_again == 0
    assert messages == snapshot


class _CaptureProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)
        self.last_messages: list[dict[str, Any]] = []

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
        del tools, model, max_tokens, temperature, on_progress, kwargs
        self.last_messages = copy.deepcopy(messages)
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_run_agent_loop_repairs_dangling_tool_calls_before_provider_chat(tmp_path: Path) -> None:
    provider = _CaptureProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )

    initial_messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_dangling",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "user", "content": "continue"},
    ]

    final_content, _, _, _, _ = asyncio.run(loop._run_agent_loop(initial_messages))
    assert final_content == "ok"

    repaired_messages = provider.last_messages
    idx_assistant = next(
        i
        for i, m in enumerate(repaired_messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    )
    injected = repaired_messages[idx_assistant + 1]
    assert injected.get("role") == "tool"
    assert injected.get("tool_call_id") == "call_dangling"
    assert injected.get("name") == "read_file"
    assert injected.get("content") == "[Tool call was interrupted and did not return a result.]"
