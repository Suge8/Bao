"""Tool registry for dynamic tool management."""

import asyncio
import copy
import inspect
import json
from dataclasses import dataclass
from typing import Any

from bao.agent.tool_result import ToolExecutionOutput, ToolExecutionResult
from bao.agent.tools._registry_execute import (
    ToolExecutionRequest,
    execution_error_result,
    invalid_params_result,
    prepare_tool_execution,
    tool_not_found_result,
)
from bao.agent.tools.base import Tool

_SLIM_SCHEMA_TOOL_THRESHOLD = 8
_SLIM_SCHEMA_BYTES_THRESHOLD = 12_000


@dataclass(frozen=True)
class ToolMetadata:
    bundle: str = "core"
    short_hint: str = ""
    aliases: tuple[str, ...] = ()
    keyword_aliases: tuple[str, ...] = ()
    auto_callable: bool = True
    summary: str = ""


class ToolRegistry:
    """Registry for agent tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._metadata: dict[str, ToolMetadata] = {}
        self._schema_cache: dict[tuple[str, bool], dict[str, Any]] = {}

    @staticmethod
    def _normalize_terms(*values: str) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = value.strip().lower()
            if not term or term in seen:
                continue
            seen.add(term)
            normalized.append(term)
        return tuple(normalized)

    @classmethod
    def _default_metadata(cls, tool: Tool) -> ToolMetadata:
        summary = tool.description.strip()
        return ToolMetadata(short_hint=summary, summary=summary)

    @classmethod
    def _coerce_metadata(cls, tool: Tool, metadata: ToolMetadata | None) -> ToolMetadata:
        base = cls._default_metadata(tool)
        if metadata is None:
            return base

        bundle = metadata.bundle.strip().lower() or base.bundle
        short_hint = metadata.short_hint.strip() or metadata.summary.strip() or base.short_hint
        summary = metadata.summary.strip() or short_hint or base.summary
        aliases = cls._normalize_terms(*metadata.aliases)
        keyword_aliases = cls._normalize_terms(*metadata.keyword_aliases)
        return ToolMetadata(
            bundle=bundle,
            short_hint=short_hint,
            aliases=aliases,
            keyword_aliases=keyword_aliases,
            auto_callable=bool(metadata.auto_callable),
            summary=summary,
        )

    def register(self, tool: Tool, *, metadata: ToolMetadata | None = None) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        self._metadata[tool.name] = self._coerce_metadata(tool, metadata)
        self._invalidate_schema_cache(tool.name)

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)
        self._metadata.pop(name, None)
        self._invalidate_schema_cache(name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_metadata(self, name: str) -> ToolMetadata | None:
        return self._metadata.get(name)

    def update_metadata(self, name: str, metadata: ToolMetadata) -> bool:
        tool = self._tools.get(name)
        if tool is None:
            return False
        self._metadata[name] = self._coerce_metadata(tool, metadata)
        return True

    def get_metadata_map(self, *, names: set[str] | None = None) -> dict[str, ToolMetadata]:
        if names is None:
            return {name: self._metadata[name] for name in self._tools if name in self._metadata}
        return {
            name: self._metadata[name]
            for name in self._tools
            if name in names and name in self._metadata
        }

    def _invalidate_schema_cache(self, name: str) -> None:
        self._schema_cache.pop((name, False), None)
        self._schema_cache.pop((name, True), None)

    def _available_tools_text(self) -> str:
        return ", ".join(sorted(self._tools.keys())) or "none"

    def _schema_for_tool(self, tool: Tool, *, slim: bool) -> dict[str, Any]:
        cache_key = (tool.name, slim)
        cached = self._schema_cache.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)

        to_schema = tool.to_schema
        params = inspect.signature(to_schema).parameters
        if "slim" in params:
            schema = to_schema(slim=slim)
        else:
            schema = to_schema()
            if slim:
                schema = Tool.slim_schema_definition(schema)
        self._schema_cache[cache_key] = copy.deepcopy(schema)
        return copy.deepcopy(schema)

    @staticmethod
    def _payload_bytes(definitions: list[dict[str, Any]]) -> int:
        return len(json.dumps(definitions, ensure_ascii=False).encode("utf-8"))

    def get_definitions(
        self,
        *,
        names: set[str] | None = None,
        slim: bool = False,
    ) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI format."""
        if names is None:
            return [self._schema_for_tool(tool, slim=slim) for tool in self._tools.values()]
        return [
            self._schema_for_tool(tool, slim=slim)
            for tool in self._tools.values()
            if tool.name in names
        ]

    def get_budgeted_definitions(
        self,
        *,
        names: set[str] | None = None,
        prefer_slim: bool | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if prefer_slim is True:
            return self.get_definitions(names=names, slim=True), True

        full = self.get_definitions(names=names, slim=False)
        if not full or prefer_slim is False:
            return full, False

        should_use_slim = len(full) >= _SLIM_SCHEMA_TOOL_THRESHOLD
        if not should_use_slim:
            should_use_slim = self._payload_bytes(full) >= _SLIM_SCHEMA_BYTES_THRESHOLD
        if should_use_slim:
            return self.get_definitions(names=names, slim=True), True
        return full, False

    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        *,
        raw_arguments: str | None = None,
        argument_parse_error: str | None = None,
    ) -> ToolExecutionOutput:
        """Execute a tool by name, returning result or error string."""
        request = ToolExecutionRequest(
            name=name,
            params=params,
            raw_arguments=raw_arguments,
            argument_parse_error=argument_parse_error,
        )
        tool = self._tools.get(request.name)
        if not tool:
            return tool_not_found_result(request, available_tools_text=self._available_tools_text())

        if request.argument_parse_error:
            return invalid_params_result(
                request,
                detail=f"failed to parse tool arguments ({request.argument_parse_error})",
            )

        try:
            prepared = prepare_tool_execution(request, tool=tool)
            if isinstance(prepared, ToolExecutionResult):
                return prepared
            return await tool.execute(**prepared)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return execution_error_result(request, error=e)

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
