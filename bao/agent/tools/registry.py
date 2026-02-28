"""Tool registry for dynamic tool management."""

import asyncio
from typing import Any

from bao.agent.tools.base import Tool


class ToolRegistry:
    """Registry for agent tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

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
