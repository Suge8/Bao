"""Shared configuration schema helpers."""

import warnings
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

ExperienceModelLiteral = Literal["utility", "main", "none"]
MemoryLearningModeLiteral = ExperienceModelLiteral
ContextManagementLiteral = Literal["off", "observe", "auto", "aggressive"]
ExecSandboxModeLiteral = Literal["full-auto", "semi-auto", "read-only"]
SlackGroupPolicyLiteral = Literal["mention", "open", "allowlist"]
SlackDmPolicyLiteral = Literal["open", "allowlist"]
SlackModeLiteral = Literal["socket"]
MochatReplyDelayModeLiteral = Literal["off", "non-mention"]
ProviderTypeLiteral = Literal["openai", "anthropic", "gemini", "openai_codex"]
ToolExposureModeLiteral = Literal["off", "auto"]
TelegramGroupPolicyLiteral = Literal["open", "mention"]
DiscordGroupPolicyLiteral = Literal["mention", "open"]
FeishuGroupPolicyLiteral = Literal["mention", "open"]


@dataclass(frozen=True)
class PolicyWarningSpec:
    model_name: str
    field_name: str
    value: str
    allowed_values: tuple[str, ...]


def warn_unknown_policy(spec: PolicyWarningSpec) -> None:
    if spec.value in spec.allowed_values:
        return
    allowed_text = ", ".join(spec.allowed_values)
    warnings.warn(
        f"Unknown {spec.model_name}.{spec.field_name} value {spec.value!r}. "
        f"Allowed values: {allowed_text}. Proceeding for compatibility.",
        UserWarning,
        stacklevel=3,
    )


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


__all__ = [
    "Base",
    "ContextManagementLiteral",
    "DiscordGroupPolicyLiteral",
    "ExecSandboxModeLiteral",
    "ExperienceModelLiteral",
    "FeishuGroupPolicyLiteral",
    "MemoryLearningModeLiteral",
    "MochatReplyDelayModeLiteral",
    "ProviderTypeLiteral",
    "SlackDmPolicyLiteral",
    "SlackGroupPolicyLiteral",
    "SlackModeLiteral",
    "TelegramGroupPolicyLiteral",
    "ToolExposureModeLiteral",
    "get_args",
    "PolicyWarningSpec",
    "warn_unknown_policy",
]
