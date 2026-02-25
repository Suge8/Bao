"""Explicit memory management tools."""

import asyncio
from typing import Any

from bao.agent.memory import MEMORY_CATEGORIES, MemoryStore
from bao.agent.tools.base import Tool


class RememberTool(Tool):
    """Store a fact into long-term memory."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    @property
    def name(self) -> str:
        return "remember"

    @property
    def description(self) -> str:
        return (
            "Save a durable fact to long-term memory. Use for user preferences, "
            "personal info, project context, or important decisions. "
            f"Categories: {', '.join(MEMORY_CATEGORIES)}."
        )
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact to remember."},
                "category": {
                    "type": "string",
                    "enum": list(MEMORY_CATEGORIES),
                    "description": "Memory category. Default: general.",
                },
            },
            "required": ["content"],
        }
    async def execute(self, **kwargs: Any) -> str:
        content = kwargs.get("content", "")
        category = kwargs.get("category", "general")
        return await asyncio.to_thread(self._memory.remember, content, category)


class ForgetTool(Tool):
    """Remove memory entries matching a query."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    @property
    def name(self) -> str:
        return "forget"

    @property
    def description(self) -> str:
        return "Remove long-term memory entries that match a query string."
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match against memory entries."},
            },
            "required": ["query"],
        }
    async def execute(self, **kwargs: Any) -> str:
        return await asyncio.to_thread(self._memory.forget, kwargs.get("query", ""))


class UpdateMemoryTool(Tool):
    """Replace content of a specific memory category."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    @property
    def name(self) -> str:
        return "update_memory"
    @property
    def description(self) -> str:
        return (
            "Replace the entire content of a memory category. "
            f"Categories: {', '.join(MEMORY_CATEGORIES)}."
        )
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string", "enum": list(MEMORY_CATEGORIES),
                    "description": "Which memory category to update.",
                },
                "content": {"type": "string", "description": "New content for this category."},
            },
            "required": ["category", "content"],
        }
    async def execute(self, **kwargs: Any) -> str:
        return await asyncio.to_thread(
            self._memory.update_memory, kwargs.get("category", ""), kwargs.get("content", "")
        )
