from __future__ import annotations

from dataclasses import dataclass

from bao.agent.tool_catalog import ToolCatalog
from bao.agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class CapabilityRegistrySnapshot:
    items: tuple[dict[str, object], ...]
    overview: dict[str, object]
    selected_id: str
    selected_item: dict[str, object]


def build_capability_registry_snapshot(
    *,
    catalog: ToolCatalog,
    config_data: dict[str, object],
    probe_results: dict[str, dict[str, object]],
    query: str,
    source_filter: str,
    selected_id: str,
) -> CapabilityRegistrySnapshot:
    all_items = catalog.list_items(config_data, probe_results)
    overview = catalog.build_overview(all_items, config_data)
    filtered_items = [
        dict(item)
        for item in all_items
        if _matches_filters(item, source_filter=source_filter, query=query)
    ]
    selected_item = next(
        (item for item in filtered_items if item.get("id") == selected_id),
        filtered_items[0] if filtered_items else {},
    )
    if selected_item:
        next_selected_id = str(selected_item.get("id") or "")
        next_selected_item = dict(selected_item)
    else:
        next_selected_id = ""
        next_selected_item = {}
    return CapabilityRegistrySnapshot(
        items=tuple(filtered_items),
        overview=dict(overview),
        selected_id=next_selected_id,
        selected_item=next_selected_item,
    )


def build_available_tool_lines(
    *,
    registry: ToolRegistry,
    selected_tool_names: list[str],
    max_lines: int = 12,
) -> list[str]:
    metadata_map = registry.get_metadata_map(names=set(selected_tool_names))
    if not metadata_map:
        return []
    visible_names = selected_tool_names[:max_lines]
    lines = []
    for name in visible_names:
        meta = metadata_map.get(name)
        if meta is None:
            continue
        hint = meta.short_hint or meta.summary or name
        lines.append(f"- {name}: {hint}")
    overflow = len(selected_tool_names) - len(visible_names)
    if overflow > 0:
        lines.append(f"- plus {overflow} more tools already exposed this turn")
    return lines


def _matches_filters(item: dict[str, object], *, source_filter: str, query: str) -> bool:
    if source_filter == "builtin" and item.get("kind") != "builtin":
        return False
    if source_filter == "mcp" and item.get("kind") != "mcp_server":
        return False
    if source_filter == "attention" and not bool(item.get("needsAttention")):
        return False
    if not query:
        return True
    haystack = str(item.get("searchText") or "").lower()
    return query in haystack
