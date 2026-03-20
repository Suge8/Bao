from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops
from rich.align import Align
from rich.console import Console
from rich.text import Text

from bao.cli._banner_layout import build_startup_banner as build_layout_banner
from bao.cli._banner_types import (
    BannerImageOverlay,
    StartupBanner,
    StartupBannerBuildOptions,
    StartupScreenModel,
)

_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.jpg"
_LOGO_BG_THRESHOLD = 14
_LOGO_BRAILLE_ALPHA_THRESHOLD = 40
_LOGO_BRIGHTNESS_BOOST = 0.18
_IMAGE_PROTOCOL_OFF_VALUES = {"0", "off", "false", "ascii"}
_BRAILLE_DOTS = (
    (0, 0, 0x01),
    (0, 1, 0x02),
    (0, 2, 0x04),
    (1, 0, 0x08),
    (1, 1, 0x10),
    (1, 2, 0x20),
    (0, 3, 0x40),
    (1, 3, 0x80),
)


@dataclass(frozen=True)
class _TerminalImageRequest:
    protocol: str
    png_data: bytes
    cols: int
    rows: int


@dataclass(frozen=True)
class _LogoOverlayRequest:
    model: StartupScreenModel
    width: int
    logo_width: int
    protocol: str | None


def detect_terminal_image_protocol(console: Console) -> str | None:
    if os.environ.get("BAO_BANNER_IMAGE", "").strip().lower() in _IMAGE_PROTOCOL_OFF_VALUES:
        return None
    if not console.is_terminal or os.environ.get("TMUX"):
        return None
    term_program = os.environ.get("TERM_PROGRAM", "")
    term = os.environ.get("TERM", "")
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term or term_program in {"ghostty", "WezTerm"} or os.environ.get("KONSOLE_VERSION"):
        return "kitty"
    if os.environ.get("ITERM_SESSION_ID") or term_program == "iTerm.app":
        return "iterm2"
    return None


def build_startup_banner(options: StartupBannerBuildOptions) -> Any:
    logo_width = _select_logo_width(options.width)
    if logo_width is None:
        return StartupBanner(renderable=build_layout_banner(options.model, width=options.width).renderable)
    overlay = _build_banner_overlay(
        _LogoOverlayRequest(
            model=options.model,
            width=options.width,
            logo_width=logo_width,
            protocol=options.detect_protocol(),
        )
    )
    logo_renderable = Align.center(
        _build_logo_placeholder(logo_width) if overlay else _build_logo_mark(logo_width)
    )
    return StartupBanner(
        renderable=build_layout_banner(
            options.model,
            width=options.width,
            logo_renderable=logo_renderable,
        ).renderable,
        overlay=overlay,
    )


def emit_banner_overlay(console: Console, overlay: BannerImageOverlay) -> None:
    moves = [f"\x1b[{overlay.move_up}A"]
    if overlay.move_right:
        moves.append(f"\x1b[{overlay.move_right}C")
    console.file.write("\x1b7" + "".join(moves) + overlay.escape + "\x1b8")
    console.file.flush()


def _build_logo_placeholder(width: int, marker: str = " ") -> Text:
    image = _make_logo_image(width)
    cols = max(1, image.width // 2)
    rows = max(1, image.height // 4)
    block = Text()
    for row in range(rows):
        if row:
            block.append("\n")
        block.append(marker * cols)
    return block


@lru_cache(maxsize=4)
def _build_logo_mark(width: int) -> Text:
    image = _make_logo_image(width)
    alpha = image.getchannel("A")
    image_px = image.load()
    alpha_px = alpha.load()
    logo = Text()
    for y in range(0, image.height, 4):
        if y:
            logo.append("\n")
        for x in range(0, image.width, 2):
            bits, red, green, blue, count = _sample_logo_braille(image_px, alpha_px, (x, y))
            if not bits:
                logo.append(" ")
                continue
            red, green, blue = _brighten_logo_rgb((red, green, blue), count)
            logo.append(chr(0x2800 + bits), style=f"bold rgb({red},{green},{blue})")
    return logo


def _resize_logo_image(image: Image.Image, width: int) -> Image.Image:
    pixel_width = max(8, width * 2)
    pixel_height = max(12, round(image.height / image.width * pixel_width))
    while pixel_height % 4:
        pixel_height += 1
    return image.resize((pixel_width, pixel_height), Image.Resampling.LANCZOS)


@lru_cache(maxsize=1)
def _load_logo_rgba() -> Image.Image:
    image = Image.open(_LOGO_PATH).convert("RGBA")
    rgb = image.convert("RGB")
    bg_color = _sample_background_color(rgb)
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg_color)).convert("L")
    alpha = diff.point(
        lambda value: 0 if value < _LOGO_BG_THRESHOLD else min(255, int((value - _LOGO_BG_THRESHOLD) * 3.6)),
        mode="L",
    )
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    pad = 6
    crop_box = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(image.width, bbox[2] + pad),
        min(image.height, bbox[3] + pad),
    )
    cropped = image.crop(crop_box)
    cropped.putalpha(alpha.crop(crop_box))
    return cropped


def _sample_background_color(rgb: Image.Image) -> tuple[int, int, int]:
    corners = ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1))
    return tuple(
        round(sum(rgb.getpixel(point)[channel] for point in corners) / len(corners))
        for channel in range(3)
    )


def _make_logo_image(width: int) -> Image.Image:
    return _resize_logo_image(_load_logo_rgba().copy(), width)


def _encode_logo_png(width: int) -> bytes:
    image = _make_logo_image(width)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_terminal_image_escape(request: _TerminalImageRequest) -> str:
    if request.protocol == "kitty":
        return _build_kitty_image_escape(request)
    return _build_iterm2_image_escape(request)


def _build_kitty_image_escape(request: _TerminalImageRequest) -> str:
    chunks = _chunk_base64(request.png_data)
    parts: list[str] = []
    for index, chunk in enumerate(chunks):
        more = 1 if index < len(chunks) - 1 else 0
        control = (
            f"a=T,f=100,c={request.cols},r={request.rows},C=1,q=2,m={more}"
            if index == 0
            else f"m={more}"
        )
        parts.append(f"\x1b_G{control};{chunk}\x1b\\")
    return "".join(parts)


def _build_iterm2_image_escape(request: _TerminalImageRequest) -> str:
    payload = base64.b64encode(request.png_data).decode("ascii")
    name = base64.b64encode(b"bao-logo.png").decode("ascii")
    return (
        "\x1b]1337;File="
        f"name={name};size={len(request.png_data)};width={request.cols};height={request.rows};inline=1;preserveAspectRatio=1:{payload}\x07"
    )


def _chunk_base64(data: bytes, *, size: int = 4096) -> list[str]:
    encoded = base64.b64encode(data).decode("ascii")
    return [encoded[index : index + size] for index in range(0, len(encoded), size)]


def _build_banner_overlay(request: _LogoOverlayRequest) -> BannerImageOverlay | None:
    if not request.protocol:
        return None
    top, left, cols, rows, panel_height = _measure_logo_overlay(request)
    escape = _build_terminal_image_escape(
        _TerminalImageRequest(request.protocol, _encode_logo_png(request.logo_width), cols, rows)
    )
    if not escape:
        return None
    return BannerImageOverlay(move_up=panel_height - top, move_right=left, escape=escape)


def _measure_logo_overlay(request: _LogoOverlayRequest) -> tuple[int, int, int, int, int]:
    marker = "\u2591"
    probe_console = Console(file=io.StringIO(), record=True, width=request.width, force_terminal=False, color_system=None)
    probe_console.print(
        build_layout_banner(
            request.model,
            width=request.width,
            logo_renderable=Align.center(_build_logo_placeholder(request.logo_width, marker=marker)),
        ).renderable
    )
    lines = probe_console.export_text().splitlines()
    marked = [(index, line) for index, line in enumerate(lines) if marker in line]
    top = marked[0][0]
    left = min(line.index(marker) for _, line in marked)
    cols = max(line.rindex(marker) - line.index(marker) + 1 for _, line in marked)
    return top, left, cols, len(marked), len(lines)


def _select_logo_width(width: int) -> int | None:
    if width >= 118:
        return 24
    if width >= 112:
        return 18
    if width >= 96:
        return 17
    return None


def _sample_logo_braille(
    image_px: Any,
    alpha_px: Any,
    point: tuple[int, int],
) -> tuple[int, int, int, int, int]:
    x, y = point
    bits = 0
    red = green = blue = count = 0
    for dx, dy, bit in _BRAILLE_DOTS:
        if alpha_px[x + dx, y + dy] <= _LOGO_BRAILLE_ALPHA_THRESHOLD:
            continue
        bits |= bit
        r, g, b, _ = image_px[x + dx, y + dy]
        red += r
        green += g
        blue += b
        count += 1
    return bits, red, green, blue, count


def _brighten_logo_rgb(rgb: tuple[int, int, int], count: int) -> tuple[int, int, int]:
    red, green, blue = rgb
    red_avg = red / count
    green_avg = green / count
    blue_avg = blue / count
    return (
        min(255, int(red_avg + (255 - red_avg) * _LOGO_BRIGHTNESS_BOOST)),
        min(255, int(green_avg + (255 - green_avg) * _LOGO_BRIGHTNESS_BOOST)),
        min(255, int(blue_avg + (255 - blue_avg) * _LOGO_BRIGHTNESS_BOOST)),
    )
