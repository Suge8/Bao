"""Context builder for assembling agent prompts."""

from __future__ import annotations

from pathlib import Path

from bao.agent.memory import DEFAULT_MEMORY_POLICY, MemoryPolicy, MemoryStore
from bao.agent.skills import SkillsLoader

from ._context_media import ContextMediaMixin
from ._context_messages import ContextMessagesMixin
from ._context_prompt import ContextPromptMixin
from ._context_runtime import (
    CHANNEL_FORMAT_HINTS,
    LazyMemoryStoreOptions,
    LazyMemoryStoreProxy,
    build_runtime_block,
    format_current_time,
)
from ._context_types import (
    AssistantMessageSpec,
    BuildMessagesRequest,
    ContextBuilderOptions,
    SystemPromptRequest,
    ToolResultMessage,
)

MAX_MEMORY_ITEMS = DEFAULT_MEMORY_POLICY.related_memory_limit
MAX_EXPERIENCE_ITEMS = DEFAULT_MEMORY_POLICY.related_experience_limit
MAX_MEMORY_CHARS = DEFAULT_MEMORY_POLICY.related_memory_chars
MAX_EXPERIENCE_CHARS = DEFAULT_MEMORY_POLICY.related_experience_chars
MAX_LONG_TERM_MEMORY_CHARS = DEFAULT_MEMORY_POLICY.long_term_chars


class ContextBuilder(ContextPromptMixin, ContextMessagesMixin, ContextMediaMixin):
    BOOTSTRAP_FILES = ["INSTRUCTIONS.md", "PERSONA.md"]
    _AVAILABLE_NOW_START = "<available_now>"
    _AVAILABLE_NOW_END = "</available_now>"

    def __init__(self, workspace: Path, options: ContextBuilderOptions | None = None):
        options = options or ContextBuilderOptions()
        self.workspace = workspace
        self.prompt_root = options.prompt_root or workspace
        self.state_root = options.state_root or workspace
        self.profile_metadata = dict(options.profile_metadata or {})
        self.memory_policy = options.memory_policy or DEFAULT_MEMORY_POLICY
        self.memory = LazyMemoryStoreProxy(
            self.state_root,
            LazyMemoryStoreOptions(
                memory_store_cls=MemoryStore,
                embedding_config=options.embedding_config,
                memory_policy=self.memory_policy,
            ),
        )
        self.skills = SkillsLoader(workspace)
        self._bootstrap_cache: dict[str, tuple[tuple[int, int, int], str]] = {}

    def close(self) -> None:
        self.memory.close()


__all__ = [
    "AssistantMessageSpec",
    "BuildMessagesRequest",
    "CHANNEL_FORMAT_HINTS",
    "ContextBuilder",
    "ContextBuilderOptions",
    "DEFAULT_MEMORY_POLICY",
    "MemoryPolicy",
    "MemoryStore",
    "SystemPromptRequest",
    "ToolResultMessage",
    "build_runtime_block",
    "format_current_time",
]
