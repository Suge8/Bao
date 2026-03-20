from __future__ import annotations

from dataclasses import dataclass

from bao.agent._skill_registry_common import (
    as_str,
    build_overview,
    build_tool_maps,
    mark_section_headers,
    matches_filters,
    sort_key,
)
from bao.agent._skill_registry_items import build_skill_item
from bao.agent.skill_catalog import SkillCatalog


@dataclass(frozen=True)
class SkillWorkspaceSnapshot:
    items: tuple[dict[str, object], ...]
    overview: dict[str, object]
    selected_id: str
    selected_item: dict[str, object]

def build_skill_workspace_snapshot(
    *,
    catalog: SkillCatalog,
    config_data: dict[str, object],
    query: str,
    source_filter: str,
    selected_id: str,
) -> SkillWorkspaceSnapshot:
    family_map, tool_map = build_tool_maps(config_data)
    records = catalog.list_records()
    items = [
        build_skill_item(record=record, family_map=family_map, tool_map=tool_map)
        for record in records
    ]
    overview = build_overview(items)
    filtered = [item for item in items if matches_filters(item, source_filter=source_filter, query=query)]
    filtered.sort(key=sort_key)
    mark_section_headers(filtered)

    selected_item = next(
        (item for item in filtered if item.get("id") == selected_id),
        filtered[0] if filtered else {},
    )
    next_selected_id = as_str(selected_item.get("id")) if selected_item else ""
    next_selected_item = dict(selected_item) if selected_item else {}
    return SkillWorkspaceSnapshot(
        items=tuple(dict(item) for item in filtered),
        overview=overview,
        selected_id=next_selected_id,
        selected_item=next_selected_item,
    )
