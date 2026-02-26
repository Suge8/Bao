"""Desktop automation tools — screenshot, click, type, scroll, drag, key press, screen info.

Requires optional dependencies: mss, pyautogui, pillow.
Install via: uv sync --extra desktop-automation

Coordinate convention
---------------------
All coordinate-based tools (click, drag, scroll) accept coordinates in the
**screenshot image space** — i.e. the pixel grid of the last captured screenshot.
Internally they are converted to pyautogui logical coordinates so the LLM never
needs to reason about Retina scale factors or downscale ratios.
"""

from __future__ import annotations

import asyncio
import base64
import io
import platform
import subprocess
import tempfile
import threading
from typing import Any

from loguru import logger

from bao.agent.tools.base import Tool

# ---------------------------------------------------------------------------
# Lazy-loaded optional deps
# ---------------------------------------------------------------------------
_mss: Any = None
_pyautogui: Any = None
_PIL_Image: Any = None

_init_lock = threading.Lock()


def _ensure_deps() -> None:
    """Lazy-import optional dependencies. Raises ImportError if missing."""
    global _mss, _pyautogui, _PIL_Image
    if _mss is not None:
        return
    with _init_lock:
        if _mss is not None:
            return  # double-check after acquiring lock
        import mss as _mss_mod
        import pyautogui as _pag_mod
        from PIL import Image as _pil_image_mod  # noqa: N813

        _pag_mod.FAILSAFE = True
        _pag_mod.PAUSE = 0.1

        _mss = _mss_mod
        _pyautogui = _pag_mod
        _PIL_Image = _pil_image_mod


# ---------------------------------------------------------------------------
# Scale factor detection (thread-safe, cached)
# ---------------------------------------------------------------------------
_scale_lock = threading.Lock()
_cached_scale: float | None = None


def _detect_scale_factor() -> float:
    """Detect HiDPI scale factor. macOS: Quartz → fallback. Others: 1.0."""
    if platform.system() != "Darwin":
        return 1.0
    # Try Quartz (most accurate)
    try:
        import AppKit  # type: ignore[import-not-found]

        screen = AppKit.NSScreen.mainScreen()
        if screen:
            return float(screen.backingScaleFactor())
    except Exception:
        pass
    # Fallback: system_profiler
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType"],
            timeout=5,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        if "Retina" in out:
            return 2.0
    except Exception:
        pass
    return 1.0


def _scale() -> float:
    global _cached_scale
    if _cached_scale is not None:
        return _cached_scale
    with _scale_lock:
        if _cached_scale is not None:
            return _cached_scale
        _cached_scale = _detect_scale_factor()
        return _cached_scale


# ---------------------------------------------------------------------------
# Screenshot-to-logical coordinate mapping (thread-safe)
# ---------------------------------------------------------------------------
_coord_lock = threading.Lock()
_coord_ratio_x: float = 1.0  # multiply screenshot-x by this → logical-x
_coord_ratio_y: float = 1.0


def _update_coord_ratios(image_w: int, image_h: int) -> None:
    """Update the screenshot→logical conversion ratios after a new capture."""
    global _coord_ratio_x, _coord_ratio_y
    _ensure_deps()
    logical_w, logical_h = _pyautogui.size()
    with _coord_lock:
        _coord_ratio_x = logical_w / image_w if image_w else 1.0
        _coord_ratio_y = logical_h / image_h if image_h else 1.0


def _to_logical(x: int, y: int) -> tuple[int, int]:
    """Convert screenshot coordinates to pyautogui logical coordinates."""
    with _coord_lock:
        return int(x * _coord_ratio_x), int(y * _coord_ratio_y)


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------
def _take_screenshot_sync(
    region: dict[str, int] | None = None,
    quality: int = 75,
    max_width: int = 1280,
) -> tuple[str, str]:
    """Capture screenshot → (temp_file_path, base64_jpeg). Runs in thread."""
    _ensure_deps()
    with _mss.mss() as sct:
        if region:
            monitor = {
                "left": region["x"], "top": region["y"],
                "width": region["width"], "height": region["height"],
            }
        else:
            monitor = sct.monitors[0]
        raw = sct.grab(monitor)
        img = _PIL_Image.frombytes("RGB", raw.size, raw.rgb)

    # Downscale for LLM viewing
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), _PIL_Image.LANCZOS)

    # Update coordinate mapping so click/drag use this screenshot's space
    _update_coord_ratios(img.width, img.height)

    # Encode JPEG
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    jpeg_bytes = buf.getvalue()

    # Save to temp file (for provider image injection)
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".jpg", prefix="bao_screenshot_"
    ) as f:
        f.write(jpeg_bytes)
        path = f.name

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    logger.info("screenshot: {}x{} → {} ({}KB)", img.width, img.height, path, len(jpeg_bytes) // 1024)
    return path, b64


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------
class ScreenshotTool(Tool):
    """Capture a screenshot of the desktop or a specific region."""

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
        if all(k in kwargs for k in ("x", "y", "width", "height")):
            region = {k: int(kwargs[k]) for k in ("x", "y", "width", "height")}
        try:
            path, _b64 = await asyncio.to_thread(_take_screenshot_sync, region)
            return f"__SCREENSHOT__:{path}"
        except Exception as e:
            logger.error("screenshot failed: {}", e)
            return f"Error: screenshot failed \u2014 {e}"


class ClickTool(Tool):
    """Click at a screen coordinate (in screenshot pixel space)."""
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
                "button": {
                    "type": "string", "enum": ["left", "right", "middle"],
                    "description": "Mouse button (default: left)",
                },
                "clicks": {
                    "type": "integer", "minimum": 1, "maximum": 3,
                    "description": "Click count (default: 1, use 2 for double-click)",
                },
            },
            "required": ["x", "y"],
        }
    async def execute(self, **kwargs: Any) -> str:
        x, y = int(kwargs["x"]), int(kwargs["y"])
        button = kwargs.get("button", "left")
        clicks = int(kwargs.get("clicks", 1))
        try:
            _ensure_deps()
            lx, ly = _to_logical(x, y)
            await asyncio.to_thread(_pyautogui.click, lx, ly, clicks=clicks, button=button)
            logger.info("click: ({},{}) -> logical ({},{}) button={}", x, y, lx, ly, button)
            return f"Clicked ({x}, {y}) button={button} clicks={clicks}"
        except Exception as e:
            logger.error("click failed: {}", e)
            return f"Error: click failed \u2014 {e}"


# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------
def _clipboard_paste(text: str) -> None:
    """Copy text to clipboard and paste via hotkey. Cross-platform."""
    _ensure_deps()
    sys_name = platform.system()
    if sys_name == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
        _pyautogui.hotkey("command", "v")
    elif sys_name == "Windows":
        # Use PowerShell Set-Clipboard for proper Unicode/CJK support
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'" ],
            check=True, timeout=5, creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        _pyautogui.hotkey("ctrl", "v")
    else:  # Linux
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode("utf-8"), check=True, timeout=5,
        )
        _pyautogui.hotkey("ctrl", "v")


class TypeTextTool(Tool):
    """Type text at the current cursor position."""
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
        return {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to type"}},
            "required": ["text"],
        }
    async def execute(self, **kwargs: Any) -> str:
        text = kwargs["text"]
        try:
            _ensure_deps()
            if any(ord(c) > 127 for c in text):
                await asyncio.to_thread(_clipboard_paste, text)
            else:
                await asyncio.to_thread(_pyautogui.typewrite, text, interval=0.02)
            preview = text[:50] + ("..." if len(text) > 50 else "")
            logger.info("type_text: {!r}", preview)
            return f"Typed: {preview}"
        except Exception as e:
            logger.error("type_text failed: {}", e)
            return f"Error: type_text failed \u2014 {e}"


class KeyPressTool(Tool):
    """Press keyboard keys or hotkey combinations."""
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
        parts = [k.strip().lower() for k in keys_str.split("+")]
        try:
            _ensure_deps()
            if len(parts) == 1:
                await asyncio.to_thread(_pyautogui.press, parts[0])
            else:
                await asyncio.to_thread(_pyautogui.hotkey, *parts)
            logger.info("key_press: {}", keys_str)
            return f"Pressed: {keys_str}"
        except Exception as e:
            logger.error("key_press failed: {}", e)
            return f"Error: key_press failed \u2014 {e}"


class ScrollTool(Tool):
    """Scroll the mouse wheel at a position."""
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
            _ensure_deps()
            if "x" in kwargs and "y" in kwargs:
                lx, ly = _to_logical(int(kwargs["x"]), int(kwargs["y"]))
                await asyncio.to_thread(_pyautogui.scroll, amount, lx, ly)
            else:
                await asyncio.to_thread(_pyautogui.scroll, amount)
            logger.info("scroll: amount={}", amount)
            return f"Scrolled {amount}"
        except Exception as e:
            logger.error("scroll failed: {}", e)
            return f"Error: scroll failed \u2014 {e}"


class DragTool(Tool):
    """Drag from one coordinate to another (screenshot pixel space)."""
    @property
    def name(self) -> str:
        return "drag"
    @property
    def description(self) -> str:
        return (
            "Drag the mouse from one point to another. "
            "Coordinates are in screenshot pixel space."
        )
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
            _ensure_deps()
            lfx, lfy = _to_logical(fx, fy)
            ltx, lty = _to_logical(tx, ty)
            await asyncio.to_thread(_pyautogui.moveTo, lfx, lfy)
            await asyncio.to_thread(
                _pyautogui.drag, ltx - lfx, lty - lfy, duration=duration,
            )
            logger.info("drag: ({},{}) -> ({},{}) duration={}", fx, fy, tx, ty, duration)
            return f"Dragged ({fx},{fy}) -> ({tx},{ty})"
        except Exception as e:
            logger.error("drag failed: {}", e)
            return f"Error: drag failed \u2014 {e}"


class GetScreenInfoTool(Tool):
    """Get screen dimensions and mouse position."""
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
        try:
            _ensure_deps()
            size = await asyncio.to_thread(_pyautogui.size)
            pos = await asyncio.to_thread(_pyautogui.position)
            with _coord_lock:
                rx, ry = _coord_ratio_x, _coord_ratio_y
            # Report in screenshot space if ratios are set, else logical
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
                f"HiDPI scale: {_scale()}"
            )
            logger.info("get_screen_info: {}x{}", sw, sh)
            return info
        except Exception as e:
            logger.error("get_screen_info failed: {}", e)
            return f"Error: get_screen_info failed \u2014 {e}"
