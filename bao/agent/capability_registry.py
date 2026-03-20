from __future__ import annotations

from dataclasses import dataclass

from bao.agent._capability_registry_common import (
    as_dict,
    matches_filters,
    normalize_list,
)
from bao.agent._capability_registry_items import DecorateItemRequest, decorate_item
from bao.agent._capability_registry_overview import (
    OverviewRequest,
    build_overview,
    configured_domains,
)
from bao.agent.tool_catalog import ToolCatalog
from bao.agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class CapabilityRegistrySnapshot:
    items: tuple[dict[str, object], ...]
    overview: dict[str, object]
    selected_id: str
    selected_item: dict[str, object]


@dataclass(frozen=True)
class CapabilityRegistryRequest:
    config_data: dict[str, object]
    probe_results: dict[str, dict[str, object]]
    query: str
    source_filter: str
    selected_id: str
    tool_observability: dict[str, object] | None = None


def build_capability_registry_snapshot(
    *,
    catalog: ToolCatalog,
    request: CapabilityRegistryRequest,
) -> CapabilityRegistrySnapshot:
    tool_observability = dict(request.tool_observability or {})
    tool_exposure = as_dict(tool_observability.get("tool_exposure")) or {}
    exposure_domains = configured_domains(request.config_data)
    enabled_domains = set(normalize_list(tool_exposure.get("enabled_domains")) or exposure_domains)
    selected_domains = set(normalize_list(tool_exposure.get("selected_domains")))
    selected_tool_names = normalize_list(tool_exposure.get("ordered_tool_names"))
    selected_tool_set = set(selected_tool_names)

    all_items = [
        decorate_item(
            DecorateItemRequest(
                item=dict(item),
                enabled_domains=enabled_domains,
                selected_domains=selected_domains,
                selected_tool_names=selected_tool_set,
                has_recent_run=bool(tool_exposure),
            )
        )
        for item in catalog.list_items(request.config_data, request.probe_results)
    ]
    overview = build_overview(
        OverviewRequest(
            items=all_items,
            config_data=request.config_data,
            tool_observability=tool_observability,
            configured_domains=exposure_domains,
            selected_tool_names=selected_tool_names,
        )
    )
    filtered_items = [
        dict(item)
        for item in all_items
        if matches_filters(item, source_filter=request.source_filter, query=request.query)
    ]
    selected_item = next(
        (item for item in filtered_items if item.get("id") == request.selected_id),
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
