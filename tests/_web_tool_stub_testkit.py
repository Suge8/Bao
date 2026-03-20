from __future__ import annotations

import sys
import types
from typing import Any


def _build_web_search_tool() -> type:
    class WebSearchTool:
        def __init__(self, search_config: Any | None = None, proxy: str | None = None):
            del search_config, proxy
            self.brave_key = None
            self.tavily_key = None
            self.exa_key = None

        @property
        def name(self) -> str:
            return "web_search"

        @property
        def description(self) -> str:
            return "stub web search"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "required": []}

        async def execute(self, **kwargs: Any) -> str:
            del kwargs
            return "stub"

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            del params
            return []

        def to_schema(self) -> dict[str, Any]:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }

    return WebSearchTool


def _build_web_fetch_tool() -> type:
    class WebFetchTool:
        def __init__(self, proxy: str | None = None, **kwargs: Any):
            del proxy, kwargs

        @property
        def name(self) -> str:
            return "web_fetch"

        @property
        def description(self) -> str:
            return "stub web fetch"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            }

        async def execute(self, **kwargs: Any) -> str:
            del kwargs
            return "stub"

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            if "url" not in params:
                return ["missing required url"]
            return []

        def to_schema(self) -> dict[str, Any]:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }

    return WebFetchTool


def install_web_tool_stub(monkeypatch: Any) -> None:
    module = types.ModuleType("bao.agent.tools.web")
    setattr(module, "WebSearchTool", _build_web_search_tool())
    setattr(module, "WebFetchTool", _build_web_fetch_tool())
    monkeypatch.setitem(sys.modules, "bao.agent.tools.web", module)
