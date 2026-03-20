from __future__ import annotations

from bao.channels.progress_text import ProgressEvent


def event(
    *,
    is_progress: bool,
    is_tool_hint: bool = False,
    clear_only: bool = False,
    scope: str | None = None,
) -> ProgressEvent:
    return ProgressEvent(
        is_progress=is_progress,
        is_tool_hint=is_tool_hint,
        clear_only=clear_only,
        scope=scope,
    )
