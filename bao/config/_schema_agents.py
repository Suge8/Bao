"""Agent configuration models."""

from pydantic import Field, model_validator

from ._schema_base import (
    Base,
    ContextManagementLiteral,
    ExperienceModelLiteral,
    MemoryLearningModeLiteral,
    PolicyWarningSpec,
    get_args,
    warn_unknown_policy,
)


class AgentMemorySettings(Base):
    recent_window: int = 100
    learning_mode: str = "utility"

    @model_validator(mode="after")
    def _warn_policies(self) -> "AgentMemorySettings":
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="AgentMemorySettings",
                field_name="learning_mode",
                value=self.learning_mode,
                allowed_values=get_args(MemoryLearningModeLiteral),
            )
        )
        return self


class AgentDefaults(Base):
    workspace: str = "~/.bao/workspace"
    model: str = ""
    utility_model: str = ""
    models: list[str] = Field(default_factory=list)
    max_tokens: int = 16000
    temperature: float = 0.1
    max_tool_iterations: int = 50
    reasoning_effort: str | None = None
    service_tier: str | None = None
    context_management: str = "auto"
    tool_output_preview_chars: int = 3000
    tool_output_offload_chars: int = 8000
    tool_output_hard_chars: int = 6000
    context_compact_bytes_est: int = 240000
    context_compact_keep_recent_tool_blocks: int = 6
    artifact_retention_days: int = 7
    send_progress: bool = True
    send_tool_hints: bool = True
    memory: AgentMemorySettings = Field(default_factory=AgentMemorySettings)
    experience_model: str | None = None
    memory_window: int | None = None

    @model_validator(mode="after")
    def _warn_policies(self) -> "AgentDefaults":
        fields_set = set(getattr(self, "model_fields_set", set()))
        memory_fields_set = set(getattr(self.memory, "model_fields_set", set()))
        if "memory" in fields_set and "learning_mode" in memory_fields_set:
            chosen_learning = self.memory.learning_mode
        elif self.experience_model not in (None, ""):
            chosen_learning = self.experience_model
        else:
            chosen_learning = self.memory.learning_mode
        if "memory" in fields_set and "recent_window" in memory_fields_set:
            chosen_recent_window = int(self.memory.recent_window)
        elif self.memory_window is not None:
            chosen_recent_window = int(self.memory_window)
        else:
            chosen_recent_window = int(self.memory.recent_window)
        self.memory.learning_mode = chosen_learning
        self.experience_model = chosen_learning
        self.memory.recent_window = chosen_recent_window
        self.memory_window = chosen_recent_window
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="AgentDefaults",
                field_name="experience_model",
                value=self.memory.learning_mode,
                allowed_values=get_args(ExperienceModelLiteral),
            )
        )
        warn_unknown_policy(
            PolicyWarningSpec(
                model_name="AgentDefaults",
                field_name="context_management",
                value=self.context_management,
                allowed_values=get_args(ContextManagementLiteral),
            )
        )
        return self


class AgentsConfig(Base):
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
