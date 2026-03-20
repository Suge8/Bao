from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from bao.agent.memory import MemoryPolicy


@dataclass(frozen=True)
class ContextBuilderOptions:
    prompt_root: Path | None = None
    state_root: Path | None = None
    embedding_config: Any = None
    memory_policy: MemoryPolicy | None = None
    profile_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SystemPromptRequest:
    skill_names: list[str] | None = None
    model: str | None = None
    channel: str | None = None
    chat_id: str | None = None


@dataclass(frozen=True)
class BuildMessagesRequest:
    history: list[dict[str, Any]]
    current_message: str
    skill_names: list[str] | None = None
    media: list[str] | None = None
    channel: str | None = None
    chat_id: str | None = None
    related_memory: list[str] | None = None
    related_experience: list[str] | None = None
    long_term_memory: str | None = None
    plan_state: dict[str, Any] | None = None
    session_notes: list[str] | None = None
    model: str | None = None


@dataclass(frozen=True)
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    result: str
    image_base64: str | None = None


@dataclass(frozen=True)
class AssistantMessageSpec:
    content: str | None
    tool_calls: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None
    thinking_blocks: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class PromptMemoryContext:
    long_term_memory: str | None = None
    related_memory: list[str] | None = None
    related_experience: list[str] | None = None


@dataclass(frozen=True)
class LazyMemoryStoreOptions:
    memory_store_cls: Any
    embedding_config: Any = None
    memory_policy: MemoryPolicy | None = None
