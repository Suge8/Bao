from __future__ import annotations

import asyncio
import tempfile
from typing import Any

from bao.agent.tool_result import (
    ToolExecutionResult,
    ToolTextResult,
    cleanup_result_file,
    tool_result_excerpt,
)
from bao.agent.tools.base import Tool
from bao.agent.tools.filesystem import ReadFileTool
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.shell import ExecTool, ExecToolOptions


class SampleTool(Tool):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def description(self) -> str:
        return "sample tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
                "mode": {"type": "string", "enum": ["fast", "full"]},
                "meta": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tag"],
                },
            },
            "required": ["query", "count"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class CastTestTool(Tool):
    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema

    @property
    def name(self) -> str:
        return "cast_test"

    @property
    def description(self) -> str:
        return "cast test"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        return str(kwargs)


class CountingSchemaTool(SampleTool):
    def __init__(self) -> None:
        self.calls: list[bool] = []

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "SampleTitle",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "query text",
                    "default": "x",
                    "examples": ["x"],
                    "minLength": 2,
                },
                "meta": {
                    "type": "object",
                    "title": "MetaTitle",
                    "properties": {
                        "tag": {"type": "string", "description": "tag"},
                        "flags": {"type": "array", "items": {"type": "string", "description": "flag"}},
                    },
                    "required": ["tag"],
                },
            },
            "required": ["query"],
        }

    def to_schema(self, *, slim: bool = False) -> dict[str, Any]:
        self.calls.append(slim)
        return super().to_schema(slim=slim)


__all__ = [
    "CastTestTool",
    "CountingSchemaTool",
    "ExecTool",
    "ExecToolOptions",
    "ReadFileTool",
    "SampleTool",
    "ToolExecutionResult",
    "ToolRegistry",
    "ToolTextResult",
    "asyncio",
    "cleanup_result_file",
    "tempfile",
    "tool_result_excerpt",
]
