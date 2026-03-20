from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bao import __version__
from bao.agent.skills import SkillsLoader
from bao.cli._banner_types import (
    StartupCapability,
    StartupScreenBuildOptions,
    StartupScreenModel,
    StartupStat,
)

_ORANGE_SOFT = "#fdba74"
_ORANGE_CREAM = "#fff7ed"
_ORANGE_INK = "#7c2d12"


@dataclass(frozen=True)
class _StatsCopy:
    channels_value: str
    channels_detail: str
    cron_value: str
    cron_detail: str
    heartbeat_value: str
    heartbeat_detail: str


def count_available_skills(workspace: Path) -> int:
    return len(SkillsLoader(workspace).list_skills(filter_unavailable=True))


def summarize_search_providers(providers: list[str]) -> str:
    if not providers:
        return "未启用"
    if len(providers) == 1:
        return providers[0].upper()
    return f"{providers[0].upper()} +{len(providers) - 1}"


def build_startup_screen_model(options: StartupScreenBuildOptions) -> StartupScreenModel:
    return StartupScreenModel(
        port=options.port,
        version=__version__,
        title="Bao 中枢",
        subtitle="记忆驱动的个人 AI 助手中枢",
        tagline="记忆原生的个人 AI 助手中枢。",
        stats=_build_stats(_build_stats_copy(options)),
        capabilities=_build_capabilities(options),
    )


def _build_stats_copy(options: StartupScreenBuildOptions) -> _StatsCopy:
    channels_value, channels_detail = _summarize_channels(options.enabled_channels)
    heartbeat_value, heartbeat_detail = _format_heartbeat(options.heartbeat_interval_s)
    cron_value = "空闲" if options.cron_jobs == 0 else f"{options.cron_jobs} 项"
    cron_detail = "无定时任务" if options.cron_jobs == 0 else "任务已加载"
    return _StatsCopy(
        channels_value=channels_value,
        channels_detail=channels_detail,
        cron_value=cron_value,
        cron_detail=cron_detail,
        heartbeat_value=heartbeat_value,
        heartbeat_detail=heartbeat_detail,
    )


def _build_stats(copy: _StatsCopy) -> tuple[StartupStat, ...]:
    return (
        StartupStat("📡", "通道", "CHANNELS", copy.channels_value, copy.channels_detail, f"bold {_ORANGE_INK} on {_ORANGE_SOFT}"),
        StartupStat("⏰", "定时", "CRON", copy.cron_value, copy.cron_detail, f"bold {_ORANGE_INK} on {_ORANGE_CREAM}"),
        StartupStat("💓", "心跳", "HEARTBEAT", copy.heartbeat_value, copy.heartbeat_detail, f"bold {_ORANGE_INK} on {_ORANGE_SOFT}"),
    )


def _build_capabilities(options: StartupScreenBuildOptions) -> tuple[StartupCapability, ...]:
    capabilities: list[StartupCapability] = []
    if options.search_providers:
        capabilities.append(
            StartupCapability(
                "🔎",
                "搜索",
                "SEARCH",
                summarize_search_providers(options.search_providers),
                f"bold {_ORANGE_INK} on {_ORANGE_SOFT}",
            )
        )
    if options.desktop_enabled:
        capabilities.append(
            StartupCapability("🖥", "桌面", "DESKTOP", "READY", f"bold {_ORANGE_INK} on {_ORANGE_CREAM}")
        )
    capabilities.append(
        StartupCapability("🧩", "技能", "SKILLS", str(options.skills_count), f"bold {_ORANGE_INK} on {_ORANGE_SOFT}")
    )
    return tuple(capabilities)


def _summarize_channels(enabled_channels: list[str]) -> tuple[str, str]:
    if not enabled_channels:
        return ("0 在线", "未启用")
    first = enabled_channels[0]
    if len(enabled_channels) == 1:
        return ("1 在线", first)
    return (f"{len(enabled_channels)} 在线", f"{first} +{len(enabled_channels) - 1}")


def _format_heartbeat(interval_s: int) -> tuple[str, str]:
    if interval_s % 3600 == 0:
        hours = interval_s // 3600
        return (f"{hours}H", f"每 {hours} 小时")
    if interval_s % 60 == 0:
        minutes = interval_s // 60
        return (f"{minutes}M", f"每 {minutes} 分钟")
    return (f"{interval_s}S", f"每 {interval_s} 秒")
