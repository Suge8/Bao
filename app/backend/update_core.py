from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any


@dataclass(frozen=True)
class ReleaseAsset:
    platform: str
    url: str
    kind: str
    sha256: str
    size: int
    silent_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    channel: str
    release_url: str
    notes_url: str
    notes_markdown: str
    published_at: str
    asset: ReleaseAsset


def detect_platform_key(sys_platform: str, machine: str) -> str | None:
    machine_key = machine.strip().lower().replace("amd64", "x86_64")
    if sys_platform == "darwin":
        if machine_key in {"arm64", "aarch64"}:
            return "macos-arm64"
        if machine_key == "x86_64":
            return "macos-x86_64"
        return None
    if sys_platform.startswith("win"):
        if machine_key in {"x86_64", "arm64"}:
            return "windows-x64"
        return None
    return None


def version_is_newer(candidate: str, current: str) -> bool:
    return _compare_versions(candidate, current) > 0


def resolve_available_release(
    feed: dict[str, Any],
    *,
    channel: str,
    current_version: str,
    platform_key: str,
) -> ReleaseInfo | None:
    channels = feed.get("channels")
    if not isinstance(channels, dict):
        raise ValueError("Feed is missing channels object")
    release = channels.get(channel)
    if not isinstance(release, dict):
        raise ValueError(f"Feed is missing channel: {channel}")

    version = _read_str(release, "version")
    if not version:
        raise ValueError(f"Feed channel {channel} is missing version")
    if not version_is_newer(version, current_version):
        return None

    platforms = release.get("platforms")
    if not isinstance(platforms, dict):
        raise ValueError(f"Feed channel {channel} is missing platforms object")
    raw_asset = platforms.get(platform_key)
    if not isinstance(raw_asset, dict):
        return None

    asset = ReleaseAsset(
        platform=platform_key,
        url=_required_str(raw_asset, "url", f"platform {platform_key} url"),
        kind=_required_str(raw_asset, "kind", f"platform {platform_key} kind"),
        sha256=_required_str(raw_asset, "sha256", f"platform {platform_key} sha256"),
        size=_required_int(raw_asset, "size", f"platform {platform_key} size"),
        silent_args=_read_str_tuple(raw_asset.get("silentArgs")),
    )
    return ReleaseInfo(
        version=version,
        channel=channel,
        release_url=_read_str(release, "releaseUrl"),
        notes_url=_read_str(release, "notesUrl"),
        notes_markdown=_read_str(release, "notesMarkdown"),
        published_at=_read_str(release, "publishedAt"),
        asset=asset,
    )


def _read_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _required_str(data: dict[str, Any], key: str, label: str) -> str:
    value = _read_str(data, key)
    if not value:
        raise ValueError(f"Feed is missing {label}")
    return value


def _required_int(data: dict[str, Any], key: str, label: str) -> int:
    value = data.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Feed has invalid {label}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError(f"Feed has invalid {label}")


def _read_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _compare_versions(left: str, right: str) -> int:
    left_parts = _tokenize_version(left)
    right_parts = _tokenize_version(right)
    for l_part, r_part in zip_longest(left_parts, right_parts, fillvalue=0):
        if l_part == r_part:
            continue
        if isinstance(l_part, int) and isinstance(r_part, int):
            return 1 if l_part > r_part else -1
        if isinstance(l_part, int):
            return 1
        if isinstance(r_part, int):
            return -1
        return 1 if str(l_part) > str(r_part) else -1
    return 0


def _tokenize_version(value: str) -> list[int | str]:
    parts = re.findall(r"\d+|[A-Za-z]+", value)
    tokens: list[int | str] = []
    for part in parts:
        if part.isdigit():
            tokens.append(int(part))
        else:
            tokens.append(part.lower())
    return tokens
