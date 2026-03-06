"""Tool registry for dynamic tool management."""

import asyncio
from dataclasses import dataclass
from typing import Any

from bao.agent.tools.base import Tool


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
        return ToolMetadata(
            bundle="core",
            short_hint=summary,
            aliases=(),
            keyword_aliases=(),
            auto_callable=True,
            summary=summary,
        )

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

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)
        self._metadata.pop(name, None)

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

    def get_definitions(self, *, names: set[str] | None = None) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI format."""
        if names is None:
            return [tool.to_schema() for tool in self._tools.values()]
        return [tool.to_schema() for tool in self._tools.values() if tool.name in names]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name, returning result or error string."""
        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(sorted(self._tools.keys())) or "none"
            return (
                f"Error: Tool '{name}' not found. Available tools: {available}."
                "\n\n[Analyze the error above and try a different approach.]"
            )

        try:
            errors = tool.validate_params(params)
            if errors:
                return (
                    f"Error: Invalid parameters for tool '{name}': "
                    + "; ".join(errors)
                    + "\n\n[Analyze the error above and try a different approach.]"
                )
            return await tool.execute(**params)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return f"Error executing {name}: {str(e)}\n\n[Analyze the error above and try a different approach.]"

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
