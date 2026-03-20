from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.config.schema import Config
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        del args, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def make_loop(tmp_path: Path, config: Config | None = None, mcp_servers: dict[str, Any] | None = None) -> AgentLoop:
    return AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers=mcp_servers or {},
        config=config,
    )


def make_tool_def(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)
