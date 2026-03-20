from __future__ import annotations

import re
from typing import Any

from ._loop_types import extract_text as _extract_text

_CODE_PATH_RE = re.compile(
    r"(?:^|[\s'\"`(])[\w./-]+\.(?:py|js|ts|tsx|jsx|sh|json|ya?ml|toml|qml|md)(?:$|[\s'\"`),])"
)
_FOLLOWUP_MAX_CHARS = 6
_ACKNOWLEDGEMENT_TEXTS = frozenset({"ok", "okay", "好的", "好", "收到", "嗯", "thanks", "thankyou"})
_DESKTOP_OVERRIDE_TOKENS = (
    "screen",
    "screenshot",
    "截图",
    "截屏",
    "屏幕",
)


class LoopRouteTextMixin:
    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            text = _extract_text(msg.get("content", ""))
            if text:
                return text.lower()
        return ""

    @staticmethod
    def _previous_user_text(messages: list[dict[str, Any]]) -> str:
        seen_latest = False
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            text = _extract_text(msg.get("content", ""))
            if not text:
                continue
            if not seen_latest:
                seen_latest = True
                continue
            return text.lower()
        return ""

    @staticmethod
    def _normalize_tool_route_text(text: str) -> str:
        return text.lower().strip()

    @staticmethod
    def _should_append_previous_context(current: str) -> bool:
        normalized = current.replace(" ", "")
        if not normalized or normalized in _ACKNOWLEDGEMENT_TEXTS:
            return False
        return len(normalized) <= _FOLLOWUP_MAX_CHARS

    def _build_tool_route_text(
        self,
        initial_messages: list[dict[str, Any]],
        extra_signal_text: str | None = None,
    ) -> str:
        current = self._normalize_tool_route_text(self._latest_user_text(initial_messages))
        if isinstance(extra_signal_text, str) and extra_signal_text.strip():
            current = f"{current} {self._normalize_tool_route_text(extra_signal_text)}".strip()
        if self._should_append_previous_context(current):
            previous = self._normalize_tool_route_text(self._previous_user_text(initial_messages))
            if previous:
                current = f"{current} {previous}".strip()
        return current

    @staticmethod
    def _has_code_path_signal(user_text: str) -> bool:
        return bool(user_text and _CODE_PATH_RE.search(user_text))

    @staticmethod
    def _has_desktop_override_signal(user_text: str) -> bool:
        normalized = user_text.lower()
        return any(token in normalized for token in _DESKTOP_OVERRIDE_TOKENS)
