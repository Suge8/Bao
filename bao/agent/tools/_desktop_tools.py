from __future__ import annotations

import asyncio
import platform
from typing import Any

from loguru import logger

from bao.agent.tools._desktop_runtime import (
    clipboard_paste,
    ensure_deps,
    scale,
    screenshot_space_info,
    take_screenshot_sync,
    to_logical,
)
from bao.agent.tools.base import Tool


class ScreenshotTool(Tool):
    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return (
            "Capture a screenshot of the entire screen or a specific region. "
            "Returns a temp file path containing the JPEG image. "
            "All coordinate tools (click/drag/scroll) accept coordinates in this "
            "screenshot's pixel space — no manual conversion needed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Left edge of region (pixels)"},
                "y": {"type": "integer", "description": "Top edge of region (pixels)"},
                "width": {"type": "integer", "description": "Width of region (pixels)"},
                "height": {"type": "integer", "description": "Height of region (pixels)"},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        region = None
        if all(key in kwargs for key in ("x", "y", "width", "height")):
            region = {key: int(kwargs[key]) for key in ("x", "y", "width", "height")}
        try:
            path, _b64, width, height, size_bytes = await asyncio.to_thread(take_screenshot_sync, region)
            logger.info("🖥️ 截屏完成 / screenshot: {}×{} → {} ({}KB)", width, height, path, size_bytes // 1024)
            return f"__SCREENSHOT__:{path}"
        except Exception as exc:
            logger.warning("⚠️ 截屏失败 / screenshot failed: {}", exc)
            return f"Error: screenshot failed \u2014 {exc}"


class ClickTool(Tool):
    @property
    def name(self) -> str:
        return "click"

    @property
    def description(self) -> str:
        return (
            "Click at a coordinate from the last screenshot. "
            "Supports left/right/middle button and single/double/triple click."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X in screenshot pixels"},
                "y": {"type": "integer", "description": "Y in screenshot pixels"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button (default: left)"},
                "clicks": {"type": "integer", "minimum": 1, "maximum": 3, "description": "Click count (default: 1, use 2 for double-click)"},
            },
            "required": ["x", "y"],
        }

    async def execute(self, **kwargs: Any) -> str:
        x, y = int(kwargs["x"]), int(kwargs["y"])
        button = kwargs.get("button", "left")
        clicks = int(kwargs.get("clicks", 1))
        try:
            _, pyautogui_mod, _ = ensure_deps()
            lx, ly = to_logical(x, y)
            await asyncio.to_thread(pyautogui_mod.click, lx, ly, clicks=clicks, button=button)
            logger.info("🖱️ 点击操作 / click: ({},{}) button={}", x, y, button)
            return f"Clicked ({x}, {y}) button={button} clicks={clicks}"
        except Exception as exc:
            logger.warning("⚠️ 点击失败 / click failed: {}", exc)
            return f"Error: click failed \u2014 {exc}"


class TypeTextTool(Tool):
    @property
    def name(self) -> str:
        return "type_text"

    @property
    def description(self) -> str:
        return (
            "Type text at the current cursor position. "
            "Supports CJK/Unicode via clipboard paste. "
            "Use click() first to focus the target input field."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"text": {"type": "string", "description": "Text to type"}}, "required": ["text"]}

    async def execute(self, **kwargs: Any) -> str:
        text = kwargs["text"]
        try:
            _, pyautogui_mod, _ = ensure_deps()
            if any(ord(char) > 127 for char in text):
                await asyncio.to_thread(clipboard_paste, text)
            else:
                await asyncio.to_thread(pyautogui_mod.typewrite, text, interval=0.02)
            preview = text[:50] + ("..." if len(text) > 50 else "")
            logger.info("⌨️ 输入文本 / type text: {!r}", preview)
            return f"Typed: {preview}"
        except Exception as exc:
            logger.warning("⚠️ 输入失败 / type failed: {}", exc)
            return f"Error: type_text failed \u2014 {exc}"


class KeyPressTool(Tool):
    @property
    def name(self) -> str:
        return "key_press"

    @property
    def description(self) -> str:
        return (
            "Press a key or hotkey combination. "
            "Examples: 'enter', 'tab', 'escape', 'command+c', 'ctrl+shift+t'. "
            "Use '+' to combine modifier keys."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "Key or combo, e.g. 'enter', 'ctrl+a', 'command+shift+s'",
                },
            },
            "required": ["keys"],
        }

    async def execute(self, **kwargs: Any) -> str:
        keys_str = kwargs["keys"]
        parts = [item.strip().lower() for item in keys_str.split("+")]
        try:
            _, pyautogui_mod, _ = ensure_deps()
            if len(parts) == 1:
                await asyncio.to_thread(pyautogui_mod.press, parts[0])
            else:
                await asyncio.to_thread(pyautogui_mod.hotkey, *parts)
            logger.info("⌨️ 按键操作 / key press: {}", keys_str)
            return f"Pressed: {keys_str}"
        except Exception as exc:
            logger.warning("⚠️ 按键失败 / key failed: {}", exc)
            return f"Error: key_press failed \u2014 {exc}"


class ScrollTool(Tool):
    @property
    def name(self) -> str:
        return "scroll"

    @property
    def description(self) -> str:
        return (
            "Scroll the mouse wheel. Positive amount scrolls up, negative scrolls down. "
            "Coordinates are in screenshot pixel space (optional)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "Scroll amount (+up, -down)"},
                "x": {"type": "integer", "description": "X in screenshot pixels (optional)"},
                "y": {"type": "integer", "description": "Y in screenshot pixels (optional)"},
            },
            "required": ["amount"],
        }

    async def execute(self, **kwargs: Any) -> str:
        amount = int(kwargs["amount"])
        try:
            _, pyautogui_mod, _ = ensure_deps()
            if "x" in kwargs and "y" in kwargs:
                lx, ly = to_logical(int(kwargs["x"]), int(kwargs["y"]))
                await asyncio.to_thread(pyautogui_mod.scroll, amount, lx, ly)
            else:
                await asyncio.to_thread(pyautogui_mod.scroll, amount)
            logger.info("🖱️ 滚动操作 / scroll: amount={}", amount)
            return f"Scrolled {amount}"
        except Exception as exc:
            logger.warning("⚠️ 滚动失败 / scroll failed: {}", exc)
            return f"Error: scroll failed \u2014 {exc}"


class DragTool(Tool):
    @property
    def name(self) -> str:
        return "drag"

    @property
    def description(self) -> str:
        return "Drag the mouse from one point to another. Coordinates are in screenshot pixel space."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "from_x": {"type": "integer", "description": "Start X"},
                "from_y": {"type": "integer", "description": "Start Y"},
                "to_x": {"type": "integer", "description": "End X"},
                "to_y": {"type": "integer", "description": "End Y"},
                "duration": {"type": "number", "description": "Seconds (default: 0.5)"},
            },
            "required": ["from_x", "from_y", "to_x", "to_y"],
        }

    async def execute(self, **kwargs: Any) -> str:
        fx, fy = int(kwargs["from_x"]), int(kwargs["from_y"])
        tx, ty = int(kwargs["to_x"]), int(kwargs["to_y"])
        duration = float(kwargs.get("duration", 0.5))
        try:
            _, pyautogui_mod, _ = ensure_deps()
            lfx, lfy = to_logical(fx, fy)
            ltx, lty = to_logical(tx, ty)
            await asyncio.to_thread(pyautogui_mod.moveTo, lfx, lfy)
            await asyncio.to_thread(pyautogui_mod.drag, ltx - lfx, lty - lfy, duration=duration)
            logger.info("🖱️ 拖拽操作 / drag: ({},{}) -> ({},{}) duration={}", fx, fy, tx, ty, duration)
            return f"Dragged ({fx},{fy}) -> ({tx},{ty})"
        except Exception as exc:
            logger.warning("⚠️ 拖拽失败 / drag failed: {}", exc)
            return f"Error: drag failed \u2014 {exc}"


class GetScreenInfoTool(Tool):
    @property
    def name(self) -> str:
        return "get_screen_info"

    @property
    def description(self) -> str:
        return (
            "Get current screen info: screenshot image dimensions (= coordinate space "
            "for click/drag/scroll), mouse position, and platform. "
            "Call this before interacting if you haven't taken a screenshot yet."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        del kwargs
        try:
            _, pyautogui_mod, _ = ensure_deps()
            size = await asyncio.to_thread(pyautogui_mod.size)
            pos = await asyncio.to_thread(pyautogui_mod.position)
            rx, ry = screenshot_space_info()
            if rx != 1.0 or ry != 1.0:
                sw = int(size.width / rx)
                sh = int(size.height / ry)
                mx = int(pos.x / rx)
                my = int(pos.y / ry)
            else:
                sw, sh = size.width, size.height
                mx, my = pos.x, pos.y
            info = (
                f"Screenshot coordinate space: {sw}x{sh}\n"
                f"Mouse position: ({mx}, {my})\n"
                f"Platform: {platform.system()}\n"
                f"HiDPI scale: {scale()}"
            )
            logger.info("🖥️ 屏幕信息 / screen info: {}×{}", sw, sh)
            return info
        except Exception as exc:
            logger.warning("⚠️ 获取失败 / info failed: {}", exc)
            return f"Error: get_screen_info failed \u2014 {exc}"
