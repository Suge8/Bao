"""Desktop automation tools facade."""

from __future__ import annotations

from bao.agent.tools._desktop_runtime import (
    clipboard_paste as _clipboard_paste,
)
from bao.agent.tools._desktop_runtime import (
    ensure_deps as _ensure_deps,
)
from bao.agent.tools._desktop_runtime import (
    scale as _scale,
)
from bao.agent.tools._desktop_runtime import (
    take_screenshot_sync as _take_screenshot_sync,
)
from bao.agent.tools._desktop_runtime import (
    to_logical as _to_logical,
)
from bao.agent.tools._desktop_tools import (
    ClickTool,
    DragTool,
    GetScreenInfoTool,
    KeyPressTool,
    ScreenshotTool,
    ScrollTool,
    TypeTextTool,
)

__all__ = [
    "ClickTool",
    "DragTool",
    "GetScreenInfoTool",
    "KeyPressTool",
    "ScreenshotTool",
    "ScrollTool",
    "TypeTextTool",
    "_clipboard_paste",
    "_ensure_deps",
    "_scale",
    "_take_screenshot_sync",
    "_to_logical",
]
