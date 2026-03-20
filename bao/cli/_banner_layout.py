from __future__ import annotations

from dataclasses import dataclass

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bao.__about__ import __logo__
from bao.cli._banner_types import StartupBanner, StartupCapability, StartupScreenModel, StartupStat

_ORANGE_BORDER = "#fb923c"
_ORANGE_STRONG = "#f97316"
_ORANGE_SOFT = "#fdba74"
_ORANGE_CREAM = "#fff7ed"
_ORANGE_MUTED = "#fed7aa"
_ORANGE_INK = "#7c2d12"
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
class _LayoutOptions:
    width: int
    hero_copy: Table
    logo: object | None
    capability_cards: list[Panel]
    stat_cards: list[Panel]


def build_startup_banner(
    model: StartupScreenModel,
    *,
    width: int,
    logo_renderable: object | None = None,
) -> StartupBanner:
    hero_copy = _build_hero_copy(model, width)
    logo = _resolve_logo_renderable(width=width, logo_renderable=logo_renderable)
    capability_cards = [_build_capability_pill(capability) for capability in model.capabilities]
    stat_cards = [_build_stat_card(stat) for stat in model.stats]
    panel = Panel.fit(
        _build_banner_body(_LayoutOptions(width, hero_copy, logo, capability_cards, stat_cards)),
        border_style=_ORANGE_BORDER,
        box=box.HEAVY,
        padding=(0, 1),
    )
    return StartupBanner(renderable=Align.center(panel))


def _build_banner_body(options: _LayoutOptions) -> Group:
    if options.width >= 112:
        return _build_wide_body(options)
    if options.width >= 96:
        return _build_medium_body(options)
    return _build_narrow_body(options)


def _build_wide_body(options: _LayoutOptions) -> Group:
    hero = Table.grid(expand=True, padding=(0, 2 if options.width >= 118 else 1))
    hero.add_column(no_wrap=True)
    hero.add_column(ratio=1)
    hero.add_row(options.logo, Align.left(options.hero_copy, vertical="middle"))
    stats = Columns(options.stat_cards, expand=True, equal=True, align="center")
    return Group(
        Align.center(Padding(hero, (0, 0, 0, _hero_optical_left_pad(options.width)))),
        Align.center(stats),
    )


def _build_medium_body(options: _LayoutOptions) -> Group:
    hero = Table.grid(padding=(0, 3))
    hero.add_column(no_wrap=True)
    hero.add_column(no_wrap=True)
    hero.add_row(options.logo, options.hero_copy)
    capabilities = Columns(options.capability_cards, expand=False, equal=True, align="center")
    stats = Columns(options.stat_cards, expand=True, equal=True, align="center")
    return Group(
        Align.center(Padding(hero, (0, 0, 0, _hero_optical_left_pad(options.width)))),
        Align.center(capabilities),
        stats,
    )


def _build_narrow_body(options: _LayoutOptions) -> Group:
    capabilities = _group_or_columns(options.capability_cards, options.width)
    stats = _group_or_columns(options.stat_cards, options.width)
    return Group(Align.center(options.hero_copy), Align.center(capabilities), Align.center(stats))


def _group_or_columns(renderables: list[Panel], width: int) -> Group | Columns:
    if width < 90:
        return Group(*renderables)
    return Columns(renderables, expand=False, equal=True, align="center")


def _build_hero_copy(model: StartupScreenModel, width: int) -> Table:
    hero_copy = Table.grid()
    hero_copy.add_row(_build_badge_row(model))
    hero_copy.add_row(_build_wordmark(wide=width >= 108))
    hero_copy.add_row(Text(model.subtitle, style=f"bold {_ORANGE_CREAM}"))
    hero_copy.add_row(Text(model.tagline, style=f"italic {_ORANGE_MUTED}"))
    if width >= 112:
        hero_copy.add_row(_build_capability_strip(model.capabilities))
    return hero_copy


def _resolve_logo_renderable(*, width: int, logo_renderable: object | None) -> object | None:
    if logo_renderable is not None:
        return logo_renderable
    return None


def _build_badge_row(model: StartupScreenModel) -> Text:
    badges = (
        (f" {__logo__} {model.title.upper()} ", f"bold {_ORANGE_INK} on {_ORANGE_SOFT}"),
        (f" v{model.version} ", f"bold {_ORANGE_CREAM} on {_ORANGE_STRONG}"),
        (f" port {model.port} ", f"bold {_ORANGE_INK} on {_ORANGE_CREAM}"),
    )
    row = Text()
    for index, (label, style) in enumerate(badges):
        if index:
            row.append(" ")
        row.append(label, style=style)
    return row


def _build_wordmark(*, wide: bool) -> Text:
    palette = (_ORANGE_CREAM, "#ffedd5", "#fed7aa", "#fdba74", "#fb923c", _ORANGE_STRONG)
    source = _BAO_WIDE if wide else _BAO
    wordmark = Text()
    for index, line in enumerate(source.strip("\n").splitlines()):
        if index:
            wordmark.append("\n")
        wordmark.append(line, style=f"bold {palette[index]}")
    return wordmark


def _build_capability_strip(capabilities: tuple[StartupCapability, ...]) -> Table:
    strip = Table.grid(padding=(0, 2))
    for _ in capabilities:
        strip.add_column(no_wrap=True, justify="left")
    strip.add_row(*[_build_compact_capability(capability) for capability in capabilities])
    return strip


def _build_compact_capability(capability: StartupCapability) -> Text:
    item = Text()
    item.append(f"{capability.icon} ", style=f"bold {_ORANGE_CREAM}")
    item.append(f"{capability.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    item.append(capability.title_en, style=f"bold {_ORANGE_MUTED}")
    item.append("  ")
    item.append(f" {capability.value} ", style=capability.accent_style)
    return item


def _build_stat_card(stat: StartupStat) -> Panel:
    heading = Text()
    heading.append(f"{stat.icon} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(f"{stat.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(stat.title_en, style=f"bold {_ORANGE_MUTED}")
    copy = Table.grid()
    copy.add_row(heading)
    copy.add_row(Text(f" {stat.value} ", style=stat.value_style))
    copy.add_row(Text(stat.detail, style=f"dim {_ORANGE_CREAM}"))
    return Panel(copy, box=box.ROUNDED, border_style=_ORANGE_BORDER, padding=(0, 1))


def _build_capability_pill(capability: StartupCapability) -> Panel:
    heading = Text()
    heading.append(f"{capability.icon} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(f"{capability.title_zh} ", style=f"bold {_ORANGE_CREAM}")
    heading.append(capability.title_en, style=f"bold {_ORANGE_MUTED}")
    copy = Table.grid(padding=(0, 1))
    copy.add_row(heading, Text(f" {capability.value} ", style=capability.accent_style))
    return Panel(copy, box=box.ROUNDED, border_style=_ORANGE_BORDER, padding=(0, 1))
def _hero_optical_left_pad(width: int) -> int:
    if width >= 118:
        return 4
    if width >= 96:
        return 2
    return 0
