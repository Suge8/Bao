"""Agent core module."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["AgentLoop", "ContextBuilder", "MemoryStore", "SkillsLoader"]


def __getattr__(name: str) -> Any:
    if name in {"loop", "context", "memory", "skills"}:
        return importlib.import_module(f"bao.agent.{name}")
    if name == "AgentLoop":
        from bao.agent.loop import AgentLoop

        return AgentLoop
    if name == "ContextBuilder":
        from bao.agent.context import ContextBuilder

        return ContextBuilder
    if name == "MemoryStore":
        from bao.agent.memory import MemoryStore

        return MemoryStore
    if name == "SkillsLoader":
        from bao.agent.skills import SkillsLoader

        return SkillsLoader
    raise AttributeError(f"module 'bao.agent' has no attribute {name!r}")
