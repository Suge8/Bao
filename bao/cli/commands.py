from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from PIL import Image, ImageChops
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bao import __logo__, __version__
from bao.agent.skills import SkillsLoader

if TYPE_CHECKING:
    from bao.config.schema import Config

app = typer.Typer(name="bao", help=f"{__logo__} Bao - Gateway", invoke_without_command=True)
console = Console()
_BANNER_EMOJI = "🍞"
_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "logo.jpg"
_LOGO_BG_THRESHOLD = 14
_LOGO_BRAILLE_ALPHA_THRESHOLD = 40
_LOGO_BRIGHTNESS_BOOST = 0.18
_IMAGE_PROTOCOL_OFF_VALUES = {"0", "off", "false", "ascii"}
_ORANGE_BORDER = "#fb923c"
_ORANGE_STRONG = "#f97316"
_ORANGE_SOFT = "#fdba74"
_ORANGE_CREAM = "#fff7ed"
_ORANGE_MUTED = "#fed7aa"
_ORANGE_INK = "#7c2d12"
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
_BAO = r"""
  ██████╗  █████╗  ██████╗
  ██╔══██╗██╔══██╗██╔═══██╗
  ██████╔╝███████║██║   ██║
  ██╔══██╗██╔══██║██║   ██║
  ██████╔╝██║  ██║╚██████╔╝
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝"""
_BAO_WIDE = r"""
  ╔██████╗   ╔█████╗   ╔██████╗
  ║██╔══██╗ ║██╔══██╗ ║██╔═══██╗
  ║██████╔╝ ║███████║ ║██║   ██║
  ║██╔══██╗ ║██╔══██║ ║██║   ██║
  ║██████╔╝ ║██║  ██║ ╚██████╔╝
  ╚═════╝   ╚═╝  ╚═╝  ╚═════╝"""


@dataclass(frozen=True)
class StartupStat:
    icon: str
    title_zh: str
    title_en: str
    value: str
    detail: str
    value_style: str


@dataclass(frozen=True)
class StartupCapability:
    icon: str
    title_zh: str
    title_en: str
    value: str
    accent_style: str


@dataclass(frozen=True)
class StartupScreenModel:
    port: int
    version: str
    title: str
    subtitle: str
    tagline: str
    stats: tuple[StartupStat, ...]
    capabilities: tuple[StartupCapability, ...]


@dataclass(frozen=True)
class BannerImageOverlay:
    move_up: int
    move_right: int
    escape: str


@dataclass(frozen=True)
class StartupBanner:
    renderable: Align
    overlay: BannerImageOverlay | None = None


def _summarize_channels(enabled_channels: list[str]) -> tuple[str, str]:
    if not enabled_channels:
        return ("0 ONLINE", "none")
    first = enabled_channels[0]
    if len(enabled_channels) == 1:
        return ("1 ONLINE", first)
    return (f"{len(enabled_channels)} ONLINE", f"{first} +{len(enabled_channels) - 1}")


def _format_heartbeat(interval_s: int) -> tuple[str, str]:
    if interval_s % 3600 == 0:
        hours = interval_s // 3600
        return (f"{hours}H", f"每 {hours} 小时")
    if interval_s % 60 == 0:
        minutes = interval_s // 60
        return (f"{minutes}M", f"每 {minutes} 分钟")
    return (f"{interval_s}S", f"每 {interval_s} 秒")


def _collect_search_providers(config: "Config") -> list[str]:
    search = config.tools.web.search
    providers = [
        name
        for name, enabled in (
            ("tavily", bool(search.tavily_api_key.get_secret_value())),
            ("brave", bool(search.brave_api_key.get_secret_value())),
            ("exa", bool(search.exa_api_key.get_secret_value())),
        )
        if enabled
    ]
    return providers


def _summarize_search_providers(providers: list[str]) -> str:
    if not providers:
        return "OFF"
    if len(providers) == 1:
        return providers[0].upper()
    return f"{providers[0].upper()} +{len(providers) - 1}"


def _count_available_skills(workspace: Path) -> int:
    return len(SkillsLoader(workspace).list_skills(filter_unavailable=True))


def _build_startup_screen_model(
    *,
    port: int,
    enabled_channels: list[str],
    cron_jobs: int,
    heartbeat_interval_s: int,
    search_providers: list[str],
    desktop_enabled: bool,
    skills_count: int,
) -> StartupScreenModel:
    channels_value, channels_detail = _summarize_channels(enabled_channels)
    heartbeat_value, heartbeat_detail = _format_heartbeat(heartbeat_interval_s)
    cron_value = "IDLE" if cron_jobs == 0 else f"{cron_jobs} JOBS"
    cron_detail = "无定时任务" if cron_jobs == 0 else "任务已加载"
    capabilities: list[StartupCapability] = []
    if search_providers:
        capabilities.append(
            StartupCapability(
                icon="🔎",
                title_zh="搜索",
                title_en="SEARCH",
                value=_summarize_search_providers(search_providers),
                accent_style=f"bold {_ORANGE_INK} on {_ORANGE_SOFT}",
            )
        )
    if desktop_enabled:
        capabilities.append(
            StartupCapability(
                icon="🖥",
                title_zh="桌面",
                title_en="DESKTOP",
                value="READY",
                accent_style=f"bold {_ORANGE_INK} on {_ORANGE_CREAM}",
            )
        )
    capabilities.append(
        StartupCapability(
            icon="🧩",
            title_zh="技能",
            title_en="SKILLS",
            value=str(skills_count),
            accent_style=f"bold {_ORANGE_INK} on {_ORANGE_SOFT}",
        )
    )
    return StartupScreenModel(
        port=port,
        version=__version__,
        title="Bao Gateway",
        subtitle="记忆驱动的个人 AI 助手网关",
        tagline="Memory-native personal agent gateway.",
        stats=(
            StartupStat(
                icon="📡",
                title_zh="通道",
                title_en="CHANNELS",
                value=channels_value,
                detail=channels_detail,
                value_style=f"bold {_ORANGE_INK} on {_ORANGE_SOFT}",
            ),
            StartupStat(
                icon="⏰",
                title_zh="定时",
                title_en="CRON",
                value=cron_value,
                detail=cron_detail,
                value_style=f"bold {_ORANGE_INK} on {_ORANGE_CREAM}",
            ),
            StartupStat(
                icon="💓",
                title_zh="心跳",
                title_en="HEARTBEAT",
                value=heartbeat_value,
                detail=heartbeat_detail,
                value_style=f"bold {_ORANGE_INK} on {_ORANGE_SOFT}",
            ),
        ),
        capabilities=tuple(capabilities),
    )


def _build_wordmark(*, wide: bool) -> Text:
    wordmark = Text()
    palette = (
        _ORANGE_CREAM,
        "#ffedd5",
        "#fed7aa",
        "#fdba74",
        "#fb923c",
        _ORANGE_STRONG,
    )
    source = _BAO_WIDE if wide else _BAO
    for index, line in enumerate(source.strip("\n").splitlines()):
        if index:
            wordmark.append("\n")
        wordmark.append(line, style=f"bold {palette[index]}")
    return wordmark


def _build_badge_row(model: StartupScreenModel) -> Text:
    badges = (
        (f" {_BANNER_EMOJI} {model.title.upper()} ", f"bold {_ORANGE_INK} on {_ORANGE_SOFT}"),
        (f" v{model.version} ", f"bold {_ORANGE_CREAM} on {_ORANGE_STRONG}"),
        (f" port {model.port} ", f"bold {_ORANGE_INK} on {_ORANGE_CREAM}"),
    )
    row = Text()
    for index, (label, style) in enumerate(badges):
        if index:
            row.append(" ")
        row.append(label, style=style)
    return row


def _build_compact_capability(capability: StartupCapability) -> Text:
    item = Text()
    item.append(f"{capability.icon} ", style=f"bold {_ORANGE_CREAM}")
    item.append(f"{capability.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    item.append(capability.title_en, style=f"bold {_ORANGE_MUTED}")
    item.append("  ")
    item.append(f" {capability.value} ", style=capability.accent_style)
    return item


def _build_capability_strip(capabilities: tuple[StartupCapability, ...]) -> Table:
    strip = Table.grid(padding=(0, 2))
    for _ in capabilities:
        strip.add_column(no_wrap=True, justify="left")
    strip.add_row(*[_build_compact_capability(capability) for capability in capabilities])
    return strip


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
    corner_points = (
        (0, 0),
        (rgb.width - 1, 0),
        (0, rgb.height - 1),
        (rgb.width - 1, rgb.height - 1),
    )
    bg_color = tuple(
        round(sum(rgb.getpixel(point)[channel] for point in corner_points) / len(corner_points))
        for channel in range(3)
    )
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg_color)).convert("L")
    alpha = diff.point(
        lambda p: 0
        if p < _LOGO_BG_THRESHOLD
        else min(255, int((p - _LOGO_BG_THRESHOLD) * 3.6)),
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


def _make_logo_image(width: int) -> Image.Image:
    return _resize_logo_image(_load_logo_rgba().copy(), width)


def _build_logo_placeholder(width: int, *, marker: str = " ") -> Text:
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
    pixel_width, pixel_height = image.size
    image_px = image.load()
    alpha_px = alpha.load()

    logo = Text()
    for y in range(0, pixel_height, 4):
        if y:
            logo.append("\n")
        for x in range(0, pixel_width, 2):
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
            if not bits:
                logo.append(" ")
                continue
            red = min(255, int(red / count + (255 - red / count) * _LOGO_BRIGHTNESS_BOOST))
            green = min(255, int(green / count + (255 - green / count) * _LOGO_BRIGHTNESS_BOOST))
            blue = min(255, int(blue / count + (255 - blue / count) * _LOGO_BRIGHTNESS_BOOST))
            logo.append(
                chr(0x2800 + bits),
                style=f"bold rgb({red},{green},{blue})",
            )
    return logo


def _encode_logo_png(width: int) -> bytes:
    image = _make_logo_image(width)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _detect_terminal_image_protocol() -> str | None:
    if os.environ.get("BAO_BANNER_IMAGE", "").strip().lower() in _IMAGE_PROTOCOL_OFF_VALUES:
        return None
    if not console.is_terminal:
        return None
    if os.environ.get("TMUX"):
        return None
    term_program = os.environ.get("TERM_PROGRAM", "")
    term = os.environ.get("TERM", "")
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term or term_program in {
        "ghostty",
        "WezTerm",
    } or os.environ.get("KONSOLE_VERSION"):
        return "kitty"
    if os.environ.get("ITERM_SESSION_ID") or term_program == "iTerm.app":
        return "iterm2"
    return None


def _chunk_base64(data: bytes, *, size: int = 4096) -> list[str]:
    encoded = base64.b64encode(data).decode("ascii")
    return [encoded[index : index + size] for index in range(0, len(encoded), size)]


def _build_kitty_image_escape(png_data: bytes, *, cols: int, rows: int) -> str:
    chunks = _chunk_base64(png_data)
    if not chunks:
        return ""
    parts: list[str] = []
    for index, chunk in enumerate(chunks):
        more = 1 if index < len(chunks) - 1 else 0
        if index == 0:
            control = f"a=T,f=100,c={cols},r={rows},C=1,q=2,m={more}"
        else:
            control = f"m={more}"
        parts.append(f"\x1b_G{control};{chunk}\x1b\\")
    return "".join(parts)


def _build_iterm2_image_escape(png_data: bytes, *, cols: int, rows: int) -> str:
    payload = base64.b64encode(png_data).decode("ascii")
    name = base64.b64encode(b"bao-logo.png").decode("ascii")
    return (
        "\x1b]1337;File="
        f"name={name};size={len(png_data)};width={cols};height={rows};inline=1;preserveAspectRatio=1:{payload}\x07"
    )


def _build_terminal_image_escape(
    protocol: str, png_data: bytes, *, cols: int, rows: int
) -> str:
    if protocol == "kitty":
        return _build_kitty_image_escape(png_data, cols=cols, rows=rows)
    return _build_iterm2_image_escape(png_data, cols=cols, rows=rows)


def _measure_logo_overlay(
    model: StartupScreenModel,
    *,
    width: int,
    logo_width: int,
    marker: str,
) -> tuple[int, int, int, int, int]:
    probe_console = Console(
        file=io.StringIO(),
        record=True,
        width=width,
        force_terminal=False,
        color_system=None,
    )
    probe_console.print(
        _build_banner(
            model,
            width=width,
            logo_renderable=Align.center(_build_logo_placeholder(logo_width, marker=marker)),
        )
    )
    lines = probe_console.export_text().splitlines()
    marked_lines = [(index, line) for index, line in enumerate(lines) if marker in line]
    top = marked_lines[0][0]
    left = min(line.index(marker) for _, line in marked_lines)
    cols = max(line.rindex(marker) - line.index(marker) + 1 for _, line in marked_lines)
    rows = len(marked_lines)
    return top, left, cols, rows, len(lines)


def _build_banner_overlay(
    model: StartupScreenModel,
    *,
    width: int,
    logo_width: int,
) -> BannerImageOverlay | None:
    protocol = _detect_terminal_image_protocol()
    if not protocol:
        return None
    marker = "\u2591"
    top, left, cols, rows, panel_height = _measure_logo_overlay(
        model, width=width, logo_width=logo_width, marker=marker
    )
    escape = _build_terminal_image_escape(
        protocol, _encode_logo_png(logo_width), cols=cols, rows=rows
    )
    if not escape:
        return None
    return BannerImageOverlay(
        move_up=panel_height - top,
        move_right=left,
        escape=escape,
    )


def _build_stat_card(stat: StartupStat) -> Panel:
    heading = Text()
    heading.append(f"{stat.icon} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(f"{stat.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(stat.title_en, style=f"bold {_ORANGE_MUTED}")
    copy = Table.grid()
    copy.add_row(heading)
    copy.add_row(Text(f" {stat.value} ", style=stat.value_style))
    copy.add_row(Text(stat.detail, style=f"dim {_ORANGE_CREAM}"))
    return Panel(
        copy,
        box=box.ROUNDED,
        border_style=_ORANGE_BORDER,
        padding=(0, 1),
    )


def _build_capability_pill(capability: StartupCapability) -> Panel:
    heading = Text()
    heading.append(f"{capability.icon} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(f"{capability.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(capability.title_en, style=f"bold {_ORANGE_MUTED}")
    copy = Table.grid(padding=(0, 1))
    copy.add_row(heading, Text(f" {capability.value} ", style=capability.accent_style))
    return Panel(copy, box=box.ROUNDED, border_style=_ORANGE_BORDER, padding=(0, 1))


def _stack_renderables(renderables: list[Panel]) -> Group:
    return Group(*renderables)


def _select_logo_width(width: int) -> int | None:
    if width >= 118:
        return 24
    if width >= 112:
        return 18
    if width >= 96:
        return 17
    return None


def _hero_optical_left_pad(width: int) -> int:
    if width >= 118:
        return 4
    if width >= 96:
        return 2
    return 0


def _build_banner(
    model: StartupScreenModel,
    *,
    width: int,
    logo_renderable: object | None = None,
) -> Align:
    wide_wordmark = width >= 108
    capability_cards = [_build_capability_pill(capability) for capability in model.capabilities]
    stat_cards = [_build_stat_card(stat) for stat in model.stats]

    hero_copy = Table.grid()
    hero_copy.add_row(_build_badge_row(model))
    hero_copy.add_row(_build_wordmark(wide=wide_wordmark))
    hero_copy.add_row(Text(model.subtitle, style=f"bold {_ORANGE_CREAM}"))
    hero_copy.add_row(Text(model.tagline, style=f"italic {_ORANGE_MUTED}"))

    logo_width = _select_logo_width(width)
    logo = logo_renderable
    if logo is None and logo_width is not None:
        logo = Align.center(_build_logo_mark(logo_width))

    if width >= 112:
        hero_copy.add_row(_build_capability_strip(model.capabilities))
        hero = Table.grid(expand=True, padding=(0, 2 if width >= 118 else 1))
        hero.add_column(no_wrap=True)
        hero.add_column(ratio=1)
        hero.add_row(
            logo,
            Align.left(hero_copy, vertical="middle"),
        )
        stats = Columns(stat_cards, expand=True, equal=True, align="center")
        body = Group(
            Align.center(Padding(hero, (0, 0, 0, _hero_optical_left_pad(width)))),
            Align.center(stats),
        )
    elif width >= 96:
        hero = Table.grid(padding=(0, 3))
        hero.add_column(no_wrap=True)
        hero.add_column(no_wrap=True)
        hero.add_row(logo, hero_copy)
        capabilities = Columns(capability_cards, expand=False, equal=True, align="center")
        stats = Columns(stat_cards, expand=True, equal=True, align="center")
        body = Group(
            Align.center(Padding(hero, (0, 0, 0, _hero_optical_left_pad(width)))),
            Align.center(capabilities),
            stats,
        )
    elif width < 90:
        capabilities = _stack_renderables(capability_cards)
        stats = _stack_renderables(stat_cards)
        body = Group(
            Align.center(hero_copy),
            Align.center(capabilities),
            Align.center(stats),
        )
    else:
        capabilities = Columns(capability_cards, expand=False, equal=True, align="center")
        stats = Columns(stat_cards, expand=False, equal=True, align="center")
        body = Group(
            Align.center(hero_copy),
            Align.center(capabilities),
            Align.center(stats),
        )
    panel = Panel.fit(
        body,
        border_style=_ORANGE_BORDER,
        box=box.HEAVY,
        padding=(0, 1),
    )
    return Align.center(panel)


def _build_startup_banner(model: StartupScreenModel, *, width: int) -> StartupBanner:
    logo_width = _select_logo_width(width)
    if logo_width is None:
        return StartupBanner(renderable=_build_banner(model, width=width))
    overlay = _build_banner_overlay(model, width=width, logo_width=logo_width)
    if overlay:
        logo_renderable = Align.center(_build_logo_placeholder(logo_width))
    else:
        logo_renderable = Align.center(_build_logo_mark(logo_width))
    return StartupBanner(
        renderable=_build_banner(model, width=width, logo_renderable=logo_renderable),
        overlay=overlay,
    )


def _emit_banner_overlay(overlay: BannerImageOverlay) -> None:
    moves = [f"\x1b[{overlay.move_up}A"]
    if overlay.move_right:
        moves.append(f"\x1b[{overlay.move_right}C")
    console.file.write("\x1b7" + "".join(moves) + overlay.escape + "\x1b8")
    console.file.flush()


def _print_startup_screen(model: StartupScreenModel) -> None:
    banner = _build_startup_banner(model, width=console.size.width)
    console.print()
    console.print(banner.renderable)
    if banner.overlay:
        _emit_banner_overlay(banner.overlay)
    console.print()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"{__logo__} Bao v{__version__}")
        raise typer.Exit()


def _make_provider(config: Config):
    from bao.providers import make_provider

    try:
        return make_provider(config)
    except ValueError as e:
        from bao.config.loader import get_config_path

        console.print(f"\n[yellow]⚠ {e}[/yellow]")
        console.print("  请在配置文件中填入 API Key / Please add your API key in:")
        console.print(f"     {get_config_path()}\n")
        raise typer.Exit(1)


def _setup_logging(verbose: bool) -> None:
    import logging

    from loguru import logger

    logger.remove()
    logging.basicConfig(level=logging.WARNING)
    for name in ("httpcore", "httpx", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:

        def _friendly_format(record):
            lvl = record["level"].name
            if lvl == "WARNING":
                return "{time:HH:mm:ss} │ <yellow>{message}</yellow>\n{exception}"
            if lvl in ("ERROR", "CRITICAL"):
                return "{time:HH:mm:ss} │ <red>{message}</red>\n{exception}"
            return "{time:HH:mm:ss} │ {message}\n{exception}"

        logger.add(sys.stderr, level="INFO", format=_friendly_format)


def run_gateway(
    port: int | None,
    verbose: bool,
    *,
    config_path: str | None = None,
    workspace: str | None = None,
) -> None:
    from bao.config import set_runtime_config_path
    from bao.config.loader import load_config
    from bao.gateway.builder import build_gateway_stack, send_startup_greeting
    from bao.profile import active_profile_context

    _setup_logging(verbose)

    if config_path:
        set_runtime_config_path(config_path)

    config = load_config()
    if workspace:
        config.agents.defaults.workspace = workspace
    profile_ctx = active_profile_context(shared_workspace=config.workspace_path)
    effective_port = port if isinstance(port, int) else int(config.gateway.port)

    provider = _make_provider(config)
    stack = build_gateway_stack(config, provider, profile_context=profile_ctx)
    cron_status = stack.cron.status()
    _print_startup_screen(
        _build_startup_screen_model(
            port=effective_port,
            enabled_channels=list(stack.channels.enabled_channels),
            cron_jobs=int(cron_status["jobs"]),
            heartbeat_interval_s=int(stack.heartbeat.interval_s),
            search_providers=_collect_search_providers(config),
            desktop_enabled=bool(config.tools.desktop.enabled),
            skills_count=_count_available_skills(config.workspace_path),
        )
    )

    async def run() -> None:
        try:
            await stack.cron.start()
            await stack.heartbeat.start()
            await asyncio.gather(
                stack.agent.run(),
                stack.channels.start_all(),
                send_startup_greeting(
                    stack.agent,
                    stack.bus,
                    stack.config,
                    channels=stack.channels,
                    session_manager=stack.session_manager,
                    profile_context=profile_ctx,
                ),
            )
        except KeyboardInterrupt:
            console.print("\n👋 正在关闭 / Shutting down...")
        finally:
            await stack.agent.close_mcp()
            stack.heartbeat.stop()
            stack.cron.stop()
            stack.agent.stop()
            await stack.channels.stop_all()

    asyncio.run(run())


@app.callback()
def main(
    port: int | None = typer.Option(None, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    version: bool = typer.Option(False, "--version", callback=version_callback, is_eager=True),
) -> None:
    _ = version
    run_gateway(port=port, verbose=verbose, config_path=config, workspace=workspace)


if __name__ == "__main__":
    app()
