"""Shared hub stack builder with no UI framework dependencies."""

from __future__ import annotations

from bao.hub import _builder_prompt as _prompt
from bao.hub import _builder_stack as _stack
from bao.hub import _builder_startup as _startup
from bao.hub import _builder_targets as _targets
from bao.hub._builder_types import (
    BuildHubStackOptions,
    DesktopStartupMessage,
    HubStack,
    StartupGreetingOptions,
)
from bao.hub._dispatcher import HubDispatcher

_build_startup_system_prompt = _prompt._build_startup_system_prompt
_build_startup_trigger = _prompt._build_startup_trigger
_extract_persona_language_tag = _prompt._extract_persona_language_tag
_generate_startup_greeting = _prompt._generate_startup_greeting
_read_instructions_text = _prompt._read_instructions_text
_read_persona_text = _prompt._read_persona_text
build_hub_stack = _stack.build_hub_stack
send_startup_greeting = _startup.send_startup_greeting
shutdown_hub_stack = _stack.shutdown_hub_stack
_collect_channel_targets = _targets._collect_channel_targets
_extract_primary_id = _targets._extract_primary_id
_extract_telegram_target_id = _targets._extract_telegram_target_id
_is_telegram_chat_id = _targets._is_telegram_chat_id
_resolve_allow_from_target = _targets._resolve_allow_from_target

__all__ = [
    "BuildHubStackOptions",
    "DesktopStartupMessage",
    "HubDispatcher",
    "HubStack",
    "StartupGreetingOptions",
    "build_hub_stack",
    "send_startup_greeting",
    "shutdown_hub_stack",
]
