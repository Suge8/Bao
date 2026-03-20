# ruff: noqa: F401
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.claudecode import ClaudeCodeDetailsTool, ClaudeCodeTool
from bao.agent.tools.coding_session_store import CodingSessionEvent
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse
from tests._provider_request_testkit import request_messages


class _DummyProvider(LLMProvider):
    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "dummy/model"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _FakeSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], str] = {}
        self.events: list[CodingSessionEvent] = []

    async def load(self, *, context_key: str, backend: str) -> str | None:
        return self.sessions.get((context_key, backend))

    async def publish(self, event: CodingSessionEvent) -> None:
        self.events.append(event)
        key = (event.context_key, event.backend)
        if event.action == "active" and event.session_id:
            self.sessions[key] = event.session_id
        elif event.action == "cleared":
            self.sessions.pop(key, None)


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
