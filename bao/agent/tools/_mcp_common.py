from __future__ import annotations

import re
from typing import Any

REMOVABLE_SCHEMA_KEYS = {"examples", "example", "default", "title", "$comment"}


def truncate_description(text: str, max_chars: int = 150) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def slim_schema(schema: Any, max_description_chars: int = 150) -> Any:
    if isinstance(schema, dict):
        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key in REMOVABLE_SCHEMA_KEYS:
                continue
            if key == "description" and isinstance(value, str):
                result[key] = truncate_description(value, max_description_chars)
                continue
            result[key] = slim_schema(value, max_description_chars)
        return result
    if isinstance(schema, list):
        return [slim_schema(item, max_description_chars) for item in schema]
    return schema


def normalize_non_bool_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def resolve_server_slim_schema(server_cfg: Any, default: bool) -> bool:
    raw_override = getattr(server_cfg, "slim_schema", None)
    return raw_override if isinstance(raw_override, bool) else default


def resolve_server_max_tools(server_cfg: Any) -> int | None:
    raw_override = normalize_non_bool_int(getattr(server_cfg, "max_tools", None))
    if raw_override is None:
        return None
    return max(raw_override, 0)


def reached_global_cap(total_registered: int, pending_count: int, max_tools: int) -> bool:
    if max_tools <= 0:
        return False
    return (total_registered + pending_count) >= max_tools


def reached_server_cap(server_count: int, pending_count: int, server_max_tools: int | None) -> bool:
    if server_max_tools is None or server_max_tools <= 0:
        return False
    return (server_count + pending_count) >= server_max_tools


def normalize_name_fragment(value: str, fallback: str) -> str:
    lowered = value.lower()
    chars = [ch if (ch.isalnum() or ch == "_") else "_" for ch in lowered]
    compact = "_".join(part for part in "".join(chars).split("_") if part)
    if not compact:
        compact = fallback
    if compact[0].isdigit():
        compact = f"n_{compact}"
    return compact[:32]


def resolve_tool_timeout_seconds(server_cfg: Any) -> int:
    raw_timeout = getattr(server_cfg, "tool_timeout_seconds", None)
    if isinstance(raw_timeout, int) and raw_timeout > 0:
        return raw_timeout
    return 30


def resolve_transport_type(server_cfg: Any) -> str | None:
    raw_type = getattr(server_cfg, "type", None)
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    command = getattr(server_cfg, "command", "")
    if isinstance(command, str) and command:
        return "stdio"
    url = getattr(server_cfg, "url", "")
    if isinstance(url, str) and url:
        return "sse" if url.rstrip("/").endswith("/sse") else "streamableHttp"
    return None


def neutral_metadata_hint(name: str) -> str:
    label = str(name).strip().replace("_", " ").replace("-", " ")
    label = re.sub(r"\s+", " ", label).strip() or "mcp tool"
    return f"MCP tool for {label}."
