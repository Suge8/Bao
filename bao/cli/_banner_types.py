from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.align import Align


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


@dataclass(frozen=True)
class StartupScreenBuildOptions:
    port: int
    enabled_channels: list[str]
    cron_jobs: int
    heartbeat_interval_s: int
    search_providers: list[str]
    desktop_enabled: bool
    skills_count: int


@dataclass(frozen=True)
class StartupBannerBuildOptions:
    model: StartupScreenModel
    width: int
    detect_protocol: Any
