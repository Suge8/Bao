from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAIN_SCOPE_PREFIX = "main"
_TOOL_SCOPE_PREFIX = "tool"
_SUBAGENT_SCOPE_PREFIX = "subagent"


def normalize_progress_scope(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    scope = value.strip()
    return scope or None


def main_progress_scope(
    *,
    channel: str,
    chat_id: str,
    metadata: Mapping[str, Any] | None,
) -> str:
    identity = _scope_identity(channel=channel, chat_id=chat_id, metadata=metadata)
    return f"{_MAIN_SCOPE_PREFIX}:{identity}"


def tool_progress_scope(
    *,
    channel: str,
    chat_id: str,
    metadata: Mapping[str, Any] | None,
) -> str:
    identity = _scope_identity(channel=channel, chat_id=chat_id, metadata=metadata)
    return f"{_TOOL_SCOPE_PREFIX}:{identity}"


def subagent_progress_scope(task_id: str) -> str:
    return f"{_SUBAGENT_SCOPE_PREFIX}:{task_id.strip()}"


def main_progress_scope_from_tool_scope(scope: str | None) -> str | None:
    normalized = normalize_progress_scope(scope)
    if not normalized:
        return None
    prefix, sep, identity = normalized.partition(":")
    if prefix != _TOOL_SCOPE_PREFIX or not sep or not identity:
        return None
    return f"{_MAIN_SCOPE_PREFIX}:{identity}"


def _scope_identity(
    *,
    channel: str,
    chat_id: str,
    metadata: Mapping[str, Any] | None,
) -> str:
    if metadata:
        token = metadata.get("_pre_saved_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        session_key = metadata.get("session_key")
        if isinstance(session_key, str) and session_key.strip():
            return session_key.strip()
    return f"{channel}:{chat_id}"
