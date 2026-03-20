# ruff: noqa: F401
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from bao.agent._loop_chat_turn import ChatOnceRequest
from bao.agent._loop_types import ToolObservabilityCounters as _ToolObservabilityCounters
from bao.agent._tool_exposure_domains import DEFAULT_TOOL_EXPOSURE_DOMAINS
from bao.agent.loop import AgentLoop
from bao.agent.tools.base import Tool
from bao.agent.tools.registry import ToolMetadata
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import ChatRequest, LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)
        self.last_request: ChatRequest | None = None

    async def chat(self, request: ChatRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def _make_loop(tmp_path: Path, mode: str, domains: list[str] | None = None) -> AgentLoop:
    cfg = Config(
        tools=ToolsConfig(
            tool_exposure=ToolExposureConfig(
                mode=mode,
                domains=list(domains or DEFAULT_TOOL_EXPOSURE_DOMAINS),
            )
        )
    )
    return AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=tmp_path, config=cfg)


def _msgs(user_text: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "test"},
        {"role": "user", "content": user_text},
    ]


class _MetadataOnlyTool(Tool):
    @property
    def name(self) -> str:
        return "acme_lookup"

    @property
    def description(self) -> str:
        return "Look up live weather information."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Lookup target"}},
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        del kwargs
        return "ok"


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
