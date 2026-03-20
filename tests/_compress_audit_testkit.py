# ruff: noqa: E402, F401
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse
from tests._provider_request_testkit import request_messages

pytest = importlib.import_module("pytest")


class DummyProvider(LLMProvider):
    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy"


def _make_loop(tmp_path: Path) -> Any:
    from bao.agent.loop import AgentLoop

    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        model="dummy",
    )
    loop._experience_mode = "auto"
    return loop


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
