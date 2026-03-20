from __future__ import annotations

import base64
import io
import platform
import subprocess
import tempfile
import threading
from typing import Any

_mss: Any = None
_pyautogui: Any = None
_PIL_Image: Any = None
_init_lock = threading.Lock()
_scale_lock = threading.Lock()
_coord_lock = threading.Lock()
_cached_scale: float | None = None
_coord_ratio_x = 1.0
_coord_ratio_y = 1.0


def ensure_deps() -> tuple[Any, Any, Any]:
    global _mss, _pyautogui, _PIL_Image
    if _mss is not None:
        return _mss, _pyautogui, _PIL_Image
    with _init_lock:
        if _mss is None:
            import mss as mss_mod
            import pyautogui as pag_mod
            from PIL import Image as pil_image_mod  # noqa: N813

            pag_mod.FAILSAFE = True
            pag_mod.PAUSE = 0.1
            _mss = mss_mod
            _pyautogui = pag_mod
            _PIL_Image = pil_image_mod
    return _mss, _pyautogui, _PIL_Image


def detect_scale_factor() -> float:
    if platform.system() != "Darwin":
        return 1.0
    try:
        import AppKit  # type: ignore[import-not-found]

        screen = AppKit.NSScreen.mainScreen()
        if screen:
            return float(screen.backingScaleFactor())
    except Exception:
        pass
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


def scale() -> float:
    global _cached_scale
    if _cached_scale is not None:
        return _cached_scale
    with _scale_lock:
        if _cached_scale is None:
            _cached_scale = detect_scale_factor()
    return _cached_scale


def update_coord_ratios(image_w: int, image_h: int) -> None:
    _, pyautogui_mod, _ = ensure_deps()
    logical_w, logical_h = pyautogui_mod.size()
    with _coord_lock:
        globals()["_coord_ratio_x"] = logical_w / image_w if image_w else 1.0
        globals()["_coord_ratio_y"] = logical_h / image_h if image_h else 1.0


def to_logical(x: int, y: int) -> tuple[int, int]:
    with _coord_lock:
        return int(x * _coord_ratio_x), int(y * _coord_ratio_y)


def screenshot_space_info() -> tuple[float, float]:
    with _coord_lock:
        return _coord_ratio_x, _coord_ratio_y


def take_screenshot_sync(
    region: dict[str, int] | None = None,
    quality: int = 75,
    max_width: int = 1280,
) -> tuple[str, str, int, int, int]:
    mss_mod, _, pil_image_mod = ensure_deps()
    with mss_mod.mss() as sct:
        monitor = (
            {
                "left": region["x"],
                "top": region["y"],
                "width": region["width"],
                "height": region["height"],
            }
            if region
            else sct.monitors[0]
        )
        raw = sct.grab(monitor)
        img = pil_image_mod.frombytes("RGB", raw.size, raw.rgb)

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), pil_image_mod.LANCZOS)

    update_coord_ratios(img.width, img.height)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    jpeg_bytes = buf.getvalue()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg", prefix="bao_screenshot_") as handle:
        handle.write(jpeg_bytes)
        path = handle.name
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return path, b64, img.width, img.height, len(jpeg_bytes)


def clipboard_paste(text: str) -> None:
    _, pyautogui_mod, _ = ensure_deps()
    sys_name = platform.system()
    if sys_name == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
        pyautogui_mod.hotkey("command", "v")
        return
    if sys_name == "Windows":
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"],
            check=True,
            timeout=5,
            creationflags=0x08000000,
        )
        pyautogui_mod.hotkey("ctrl", "v")
        return
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text.encode("utf-8"),
        check=True,
        timeout=5,
    )
    pyautogui_mod.hotkey("ctrl", "v")
