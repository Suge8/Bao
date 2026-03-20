from __future__ import annotations

from bao.agent._tool_catalog_builtin import build_builtin_item
from bao.agent._tool_catalog_common import build_overview, sort_key
from bao.agent._tool_catalog_mcp import build_mcp_server_items
from bao.agent._tool_catalog_specs import BUILTIN_TOOL_FAMILIES
from bao.browser import get_browser_capability_state


class ToolCatalog:
    def list_items(
        self,
        config_data: dict[str, object],
        probe_results: dict[str, dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        probes = probe_results or {}
        items = [
            build_builtin_item(spec, config_data, browser_state_fn=get_browser_capability_state)
            for spec in BUILTIN_TOOL_FAMILIES
        ]
        items.extend(build_mcp_server_items(config_data, probes))
        items.sort(key=sort_key)
        return items

    def build_overview(
        self,
        items: list[dict[str, object]],
        config_data: dict[str, object],
    ) -> dict[str, object]:
        return build_overview(items, config_data)
