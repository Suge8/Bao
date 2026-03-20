from __future__ import annotations

from dataclasses import dataclass

from bao.agent._capability_registry_common import (
    _OBSERVABILITY_FIELDS,
    as_dict,
    as_str,
    flatten_localized,
    get_path,
    localized,
    localized_label,
)
from bao.agent._tool_exposure_domains import (
    DEFAULT_TOOL_EXPOSURE_DOMAINS,
    TOOL_DOMAIN_CORE,
    TOOL_EXPOSURE_DOMAIN_DESCRIPTIONS,
    TOOL_EXPOSURE_DOMAIN_LABELS,
    domain_required_tools,
    normalize_tool_exposure_domains,
)


@dataclass(frozen=True)
class OverviewRequest:
    items: list[dict[str, object]]
    config_data: dict[str, object]
    tool_observability: dict[str, object]
    configured_domains: list[str]
    selected_tool_names: list[str]


def build_overview(request: OverviewRequest) -> dict[str, object]:
    counts = _overview_counts(request.items)
    tools_cfg = as_dict(get_path(request.config_data, "tools", {})) or {}
    exposure = as_dict(tools_cfg.get("toolExposure")) or {}
    return {
        **counts,
        "toolExposureMode": as_str(exposure.get("mode"), "off") or "off",
        "toolExposureDomains": request.configured_domains,
        "restrictToWorkspace": bool(tools_cfg.get("restrictToWorkspace")),
        "desktopEnabled": bool(get_path(request.config_data, "tools.desktop.enabled", True)),
        "summaryMetrics": _summary_metrics(counts, len(request.selected_tool_names)),
        "exposureDomainOptions": [
            {
                "key": domain,
                "displayLabel": localized_label(TOOL_EXPOSURE_DOMAIN_LABELS, domain),
                "descriptionDisplay": localized_label(TOOL_EXPOSURE_DOMAIN_DESCRIPTIONS, domain),
                "closureSummaryDisplay": localized(
                    f"默认闭环 {len(domain_required_tools(domain))} 个工具",
                    f"{len(domain_required_tools(domain))} required tools in the default closure",
                ),
                "requiredToolCount": len(domain_required_tools(domain)),
                "locked": domain == TOOL_DOMAIN_CORE,
            }
            for domain in DEFAULT_TOOL_EXPOSURE_DOMAINS
        ],
        "observability": observability_summary(request.tool_observability),
    }


def _overview_counts(items: list[dict[str, object]]) -> dict[str, int]:
    builtin_count = sum(1 for item in items if item.get("kind") == "builtin")
    server_count = sum(1 for item in items if item.get("kind") == "mcp_server")
    attention_count = sum(1 for item in items if bool(item.get("needsAttention")))
    available_count = sum(1 for item in items if item.get("kind") == "builtin" and item.get("runtimeState") == "available")
    healthy_mcp_count = sum(1 for item in items if item.get("kind") == "mcp_server" and item.get("status") == "healthy")
    return {
        "builtinCount": builtin_count,
        "mcpServerCount": server_count,
        "attentionCount": attention_count,
        "runningNowCount": healthy_mcp_count,
        "availableCount": available_count,
    }


def _summary_metrics(counts: dict[str, int], selected_count: int) -> list[dict[str, object]]:
    return [
        {"key": "available", "displayLabel": localized("当前可用", "Available now"), "value": counts["availableCount"], "tone": "#F97316"},
        {"key": "recent_exposure", "displayLabel": localized("最近暴露", "Exposed recently"), "value": selected_count, "tone": "#34D399"},
        {"key": "mcp_connected", "displayLabel": localized("MCP 已连通", "MCP connected"), "value": counts["runningNowCount"], "tone": "#60A5FA"},
        {"key": "attention", "displayLabel": localized("需处理", "Needs attention"), "value": counts["attentionCount"], "tone": "#EF4444"},
    ]


def observability_summary(tool_observability: dict[str, object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, label_pair in _OBSERVABILITY_FIELDS:
        value = tool_observability.get(key)
        if value is None:
            continue
        text = f"{value:.2f}" if isinstance(value, float) else str(value)
        items.append({"label": flatten_localized(localized(*label_pair)), "value": text})
    return items


def configured_domains(config_data: dict[str, object]) -> list[str]:
    return normalize_tool_exposure_domains(get_path(config_data, "tools.toolExposure.domains", []))
