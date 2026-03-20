from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

DISPLAY_NAME_PATTERN = re.compile(r"^(.+?)\s+\(")

RunCommandFn = Callable[..., Awaitable[dict[str, Any]]]


async def load_agent_aliases(
    *,
    cache: dict[str, dict[str, str]],
    cwd: Path,
    timeout_seconds: int,
    run_command: RunCommandFn,
) -> dict[str, str]:
    cache_key = str(cwd)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await run_command(
        cmd=["opencode", "debug", "config"],
        cwd=cwd,
        timeout_seconds=min(timeout_seconds, 30),
    )
    if result["timed_out"] or result["returncode"] != 0:
        cache[cache_key] = {}
        return {}

    try:
        payload = json.loads(result["stdout"])
    except (TypeError, ValueError, json.JSONDecodeError):
        cache[cache_key] = {}
        return {}

    agents = payload.get("agent") if isinstance(payload, dict) else None
    if not isinstance(agents, dict):
        cache[cache_key] = {}
        return {}

    aliases: dict[str, str] = {}
    short_name_counts: dict[str, int] = {}
    short_name_targets: dict[str, str] = {}
    for display_name in agents:
        if not isinstance(display_name, str):
            continue
        normalized_display = display_name.strip()
        if not normalized_display:
            continue
        aliases[normalized_display.casefold()] = normalized_display
        match = DISPLAY_NAME_PATTERN.match(normalized_display)
        if not match:
            continue
        short_name = match.group(1).strip().casefold()
        if not short_name:
            continue
        short_name_counts[short_name] = short_name_counts.get(short_name, 0) + 1
        short_name_targets[short_name] = normalized_display

    for short_name, count in short_name_counts.items():
        if count == 1:
            aliases[short_name] = short_name_targets[short_name]

    cache[cache_key] = aliases
    return aliases


async def resolve_agent_alias(
    *,
    cache: dict[str, dict[str, str]],
    cwd: Path,
    agent_name: str,
    timeout_seconds: int,
    run_command: RunCommandFn,
) -> str:
    trimmed = agent_name.strip()
    if not trimmed:
        return agent_name
    aliases = await load_agent_aliases(
        cache=cache,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        run_command=run_command,
    )
    if not aliases:
        return agent_name
    return aliases.get(trimmed.casefold(), agent_name)
