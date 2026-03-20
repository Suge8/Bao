"""Versioned config migration pipeline.

Each migration function transforms config data from version N to N+1.
Functions are pure data transforms — no file IO, no network calls.

Current version: 6
  v0 (implicit) → v1: legacy provider keys + tools field renames
  v1 → v2: (reserved for future migrations)
  v2 → v3: add tools.toolExposure defaults
  v3 → v4: move memoryWindow / experienceModel under agents.defaults.memory
  v4 → v5: rename gateway config block to hub
  v5 → v6: replace tools.toolExposure.bundles with domains
"""

from collections.abc import Callable
from typing import Any

CURRENT_VERSION = 6


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
    web_cfg = tools.get("web", {})
    if not isinstance(web_cfg, dict):
        web_cfg = {}
    search = web_cfg.get("search", {})
    if not isinstance(search, dict):
        search = {}
    if "apiKey" in search and "braveApiKey" not in search:
        search["braveApiKey"] = search.pop("apiKey")
    if "tavilyKey" in search and "tavilyApiKey" not in search:
        search["tavilyApiKey"] = search.pop("tavilyKey")

    return data


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Reserved for future migrations. Currently a no-op."""
    return data


def _migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        return data
    exposure = tools.get("toolExposure")
    if not isinstance(exposure, dict):
        tools["toolExposure"] = {
            "mode": "off",
            "domains": [
                "core",
                "messaging",
                "handoff",
                "web_research",
                "desktop_automation",
                "coding_backend",
            ],
        }
        return data
    exposure.setdefault("mode", "off")
    domains = exposure.get("domains")
    if not isinstance(domains, list):
        exposure["domains"] = [
            "core",
            "messaging",
            "handoff",
            "web_research",
            "desktop_automation",
            "coding_backend",
        ]
    return data


def _migrate_v3_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return data
    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        return data
    memory = defaults.get("memory")
    if not isinstance(memory, dict):
        memory = {}
        defaults["memory"] = memory
    if "recentWindow" not in memory and "memoryWindow" in defaults:
        memory["recentWindow"] = defaults.get("memoryWindow")
    if "learningMode" not in memory and "experienceModel" in defaults:
        memory["learningMode"] = defaults.get("experienceModel")
    defaults.pop("memoryWindow", None)
    defaults.pop("experienceModel", None)
    return data


def _migrate_v4_to_v5(data: dict[str, Any]) -> dict[str, Any]:
    hub = data.get("hub")
    gateway = data.get("gateway")
    if "hub" not in data and isinstance(gateway, dict):
        data["hub"] = gateway
    if isinstance(hub, dict) and "gateway" in data:
        data.pop("gateway", None)
    elif "hub" in data:
        data.pop("gateway", None)
    return data


def _migrate_v5_to_v6(data: dict[str, Any]) -> dict[str, Any]:
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        return data
    exposure = tools.get("toolExposure")
    if not isinstance(exposure, dict):
        return data
    raw_domains = exposure.get("domains")
    if isinstance(raw_domains, list):
        exposure.pop("bundles", None)
        return data
    raw_bundles = exposure.get("bundles")
    if isinstance(raw_bundles, list):
        domains: list[str] = []
        for bundle in raw_bundles:
            normalized = str(bundle).strip().lower()
            if normalized == "core":
                domains.extend(["core", "messaging", "handoff"])
            elif normalized == "web":
                domains.append("web_research")
            elif normalized == "desktop":
                domains.append("desktop_automation")
            elif normalized == "code":
                domains.append("coding_backend")
        deduped_domains = list(dict.fromkeys(domains))
        if deduped_domains:
            exposure["domains"] = deduped_domains
        else:
            exposure["domains"] = [
                "core",
                "messaging",
                "handoff",
                "web_research",
                "desktop_automation",
                "coding_backend",
            ]
    else:
        exposure["domains"] = [
            "core",
            "messaging",
            "handoff",
            "web_research",
            "desktop_automation",
            "coding_backend",
        ]
    exposure.pop("bundles", None)
    return data


# Ordered migration chain: (from_version, to_version, function)
_MIGRATIONS: list[tuple[int, int, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    (0, 1, _migrate_v0_to_v1),
    (1, 2, _migrate_v1_to_v2),
    (2, 3, _migrate_v2_to_v3),
    (3, 4, _migrate_v3_to_v4),
    (4, 5, _migrate_v4_to_v5),
    (5, 6, _migrate_v5_to_v6),
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
            warnings.append(f"Migrated config v{from_v} → v{to_v}")

    data["config_version"] = CURRENT_VERSION
    return data, warnings
