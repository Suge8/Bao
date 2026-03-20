from __future__ import annotations

import asyncio

from bao.agent.tools.base import Tool
from bao.agent.tools.registry import ToolRegistry


class _NamedTool(Tool):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} tool"

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs: object) -> str:
        return str(kwargs.get("text", ""))

def test_registry_allows_edit_file_without_approval_gate() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("edit_file"))

    result = asyncio.run(registry.execute("edit_file", {"text": "done"}))

    assert result == "done"


def test_registry_allows_coding_agent_without_approval_gate() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("coding_agent"))

    result = asyncio.run(registry.execute("coding_agent", {"text": "done"}))

    assert result == "done"


def test_registry_allows_exec_without_approval_gate() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("exec"))

    result = asyncio.run(registry.execute("exec", {"text": "done"}))

    assert result == "done"


def test_registry_allows_send_to_session_without_approval_gate() -> None:
    registry = ToolRegistry()
    registry.register(_NamedTool("send_to_session"))

    result = asyncio.run(registry.execute("send_to_session", {"text": "hello"}))

    assert result == "hello"
