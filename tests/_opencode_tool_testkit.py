from __future__ import annotations

import asyncio
from typing import Any

from bao.agent.tools.coding_session_store import CodingSessionEvent
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        del args, kwargs
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "dummy/model"


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeSessionStore:
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
            return
        if event.action == "cleared":
            self.sessions.pop(key, None)


def make_run_result(result: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "timed_out": False,
        "returncode": 0,
        "stdout": "",
        "stderr": "",
    }
    if result:
        payload.update(result)
    return payload
