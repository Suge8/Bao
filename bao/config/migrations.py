"""Versioned config migration pipeline.

Each migration function transforms config data from version N to N+1.
Functions are pure data transforms — no file IO, no network calls.

Current version: 2
  v0 (implicit) → v1: legacy provider keys + tools field renames
  v1 → v2: (reserved for future migrations)
"""

from collections.abc import Callable
from typing import Any

CURRENT_VERSION = 2


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate legacy provider keys and tools field renames."""
    # --- providers: old fixed-key format → new dict+type format ---
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        return data
    old_key_map = {"openaiCompatible": "openai", "openai_compatible": "openai"}
    for old_key, new_name in old_key_map.items():
        if old_key in providers:
            cfg = providers.pop(old_key)
            cfg.setdefault("type", "openai")
            providers.setdefault(new_name, cfg)
    for name in ("anthropic", "gemini"):
        if name in providers and isinstance(providers[name], dict):
            providers[name].setdefault("type", name)

    # --- tools migrations ---
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        return data
    exec_cfg = tools.get("exec", {})
    if not isinstance(exec_cfg, dict):
        exec_cfg = {}
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    search = tools.get("web", {}).get("search", {})
    if "apiKey" in search and "braveApiKey" not in search:
        search["braveApiKey"] = search.pop("apiKey")
    if "tavilyKey" in search and "tavilyApiKey" not in search:
        search["tavilyApiKey"] = search.pop("tavilyKey")

    return data


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Reserved for future migrations. Currently a no-op."""
    return data


# Ordered migration chain: (from_version, to_version, function)
_MIGRATIONS: list[tuple[int, int, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    (0, 1, _migrate_v0_to_v1),
    (1, 2, _migrate_v1_to_v2),
]


def migrate_config(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply all necessary migrations to bring config data to CURRENT_VERSION.

    Returns:
        (migrated_data, warnings) — warnings list describes what was migrated.
    """
    if not isinstance(data, dict):
        return {}, ["Config data is not a dict, using defaults."]

    raw_version = data.get("config_version")
    try:
        version = int(raw_version) if raw_version is not None else 0
    except (TypeError, ValueError):
        version = 0

    warnings: list[str] = []

    if version > CURRENT_VERSION:
        warnings.append(
            f"Config version {version} is newer than supported {CURRENT_VERSION}. "
            "Some settings may be ignored."
        )
        return data, warnings

    for from_v, to_v, fn in _MIGRATIONS:
        if version < to_v:
            data = fn(data)
            if from_v < CURRENT_VERSION - 1:  # Only warn for non-trivial migrations
                warnings.append(f"Migrated config v{from_v} → v{to_v}")

    data["config_version"] = CURRENT_VERSION
    return data, warnings
