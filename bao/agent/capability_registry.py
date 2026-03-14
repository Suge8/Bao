from __future__ import annotations

from dataclasses import dataclass

from bao.agent.tool_catalog import ToolCatalog
from bao.agent.tools.registry import ToolRegistry

_DEFAULT_BUNDLES = ("core", "web", "desktop", "code")
_BUNDLE_LABELS = {
    "core": ("核心", "Core"),
    "web": ("网页", "Web"),
    "desktop": ("桌面", "Desktop"),
    "code": ("代码", "Code"),
    "mcp": ("MCP", "MCP"),
}
_CAPABILITY_LABELS = {
    "Filesystem": ("文件系统", "Filesystem"),
    "Workspace": ("工作区", "Workspace"),
    "Authoring": ("编辑", "Authoring"),
    "Shell": ("命令行", "Shell"),
    "Local host": ("本机", "Local host"),
    "Diagnostics": ("诊断", "Diagnostics"),
    "Codegen": ("代码生成", "Codegen"),
    "Refactor": ("重构", "Refactor"),
    "Debug": ("调试", "Debug"),
    "Search": ("搜索", "Search"),
    "Fetch": ("抓取", "Fetch"),
    "Browser": ("浏览器", "Browser"),
    "Embeddings": ("向量", "Embeddings"),
    "Retrieval": ("检索", "Retrieval"),
    "Memory": ("记忆", "Memory"),
    "Image": ("图像", "Image"),
    "Creative": ("创作", "Creative"),
    "Generation": ("生成", "Generation"),
    "Persistence": ("持久化", "Persistence"),
    "Curation": ("整理", "Curation"),
    "Plan": ("计划", "Plan"),
    "Delegate": ("委派", "Delegate"),
    "Track": ("追踪", "Track"),
    "Messaging": ("消息", "Messaging"),
    "Support": ("支持", "Support"),
    "Schedule": ("调度", "Schedule"),
    "Reminder": ("提醒", "Reminder"),
    "Automation": ("自动化", "Automation"),
    "Desktop": ("桌面", "Desktop"),
    "Input": ("输入", "Input"),
    "Visual": ("视觉", "Visual"),
    "External": ("外部", "External"),
    "MCP": ("MCP", "MCP"),
    "STDIO": ("STDIO", "STDIO"),
    "HTTP": ("HTTP", "HTTP"),
    "Setup": ("待配置", "Setup"),
}
_STATUS_LABELS = {
    "healthy": ("已连接", "Connected"),
    "ready": ("当前可用", "Available"),
    "limited": ("部分可用", "Partially ready"),
    "configured": ("已配置", "Configured"),
    "disabled": ("已关闭", "Disabled"),
    "needs_setup": ("待配置", "Needs setup"),
    "unavailable": ("不可用", "Unavailable"),
    "blocked": ("受阻", "Blocked"),
    "error": ("异常", "Error"),
}
_STATUS_TONES = {
    "healthy": "#34D399",
    "ready": "#F97316",
    "limited": "#F59E0B",
    "configured": "#60A5FA",
    "disabled": "#F97316",
    "needs_setup": "#F97316",
    "unavailable": "#F97316",
    "blocked": "#EF4444",
    "error": "#EF4444",
}
_EXPOSURE_LABELS = {
    "exposed_last_run": ("最近暴露", "Exposed recently"),
    "eligible_not_selected": ("最近未选中", "Not used recently"),
    "bundle_disabled": ("未参与自动暴露", "Bundle disabled"),
    "no_recent_run": ("暂无最近运行", "No recent run"),
}
_RUNTIME_STATE_LABELS = {
    "available": ("当前环境可用", "Available in this environment"),
    "configured_only": ("已配置，待验证", "Configured, not validated"),
    "disabled": ("当前关闭", "Disabled"),
    "needs_setup": ("还缺配置", "Needs setup"),
    "blocked": ("被依赖或环境阻塞", "Blocked by environment"),
    "error": ("最近一次运行失败", "Recent run failed"),
    "unavailable": ("当前环境不可用", "Unavailable in this environment"),
    "unknown": ("状态未知", "Unknown"),
}
_OBSERVABILITY_FIELDS = (
    ("tool_calls_total", ("工具调用", "Tool calls")),
    ("tool_calls_error", ("工具错误", "Tool errors")),
    ("retry_rate_proxy", ("重试率", "Retry rate")),
)


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
    diagnostics_snapshot: dict[str, object] | None = None,
) -> CapabilityRegistrySnapshot:
    tool_observability = _tool_observability_from_snapshot(diagnostics_snapshot or {})
    tool_exposure = _as_dict(tool_observability.get("tool_exposure")) or {}
    configured_bundles = _configured_bundles(config_data)
    enabled_bundles = set(_normalize_list(tool_exposure.get("enabled_bundles")) or configured_bundles)
    selected_bundles = set(_normalize_list(tool_exposure.get("selected_bundles")))
    selected_tool_names = _normalize_list(tool_exposure.get("ordered_tool_names"))
    selected_tool_set = set(selected_tool_names)

    all_items = [
        _decorate_item(
            dict(item),
            enabled_bundles=enabled_bundles,
            selected_bundles=selected_bundles,
            selected_tool_names=selected_tool_set,
            has_recent_run=bool(tool_exposure),
        )
        for item in catalog.list_items(config_data, probe_results)
    ]
    overview = _build_overview(
        items=all_items,
        config_data=config_data,
        tool_observability=tool_observability,
        configured_bundles=configured_bundles,
        selected_tool_names=selected_tool_names,
    )
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


def _decorate_item(
    item: dict[str, object],
    *,
    enabled_bundles: set[str],
    selected_bundles: set[str],
    selected_tool_names: set[str],
    has_recent_run: bool,
) -> dict[str, object]:
    capabilities = _normalize_list(item.get("capabilities"))
    item["displayCapabilities"] = [_localized_label(_CAPABILITY_LABELS, value) for value in capabilities]
    bundle = _as_str(item.get("bundle")).lower()
    item["displayBundleLabel"] = _localized_label(_BUNDLE_LABELS, bundle)
    item["displayStatusLabel"] = _localized_label(_STATUS_LABELS, _as_str(item.get("status")))
    item["runtimeState"] = _runtime_state(item)
    item["runtimeStateDisplay"] = _runtime_state_display(item)

    included_tools = _normalize_list(item.get("includedTools"))
    matched_tools = [name for name in included_tools if name in selected_tool_names]
    exposure_state = _exposure_state(
        item=item,
        enabled_bundles=enabled_bundles,
        selected_bundles=selected_bundles,
        matched_tools=matched_tools,
        has_recent_run=has_recent_run,
    )
    item["exposureState"] = exposure_state
    item["exposureStateDisplay"] = _localized_label(_EXPOSURE_LABELS, exposure_state)
    item["recentExposureTools"] = matched_tools
    item["exposureSummaryDisplay"] = _exposure_summary(item, exposure_state, matched_tools)

    attention_reason, attention_action = _attention_copy(item)
    item["attentionReasonDisplay"] = attention_reason
    item["attentionActionDisplay"] = attention_action
    item["includesSummaryDisplay"] = _includes_summary(item)
    item["badges"] = _badge_items(item, exposure_state)
    item["searchText"] = (
        f"{item.get('searchText', '')} "
        f"{_flatten_localized(item['displayStatusLabel'])} "
        f"{_flatten_localized(item['runtimeStateDisplay'])} "
        f"{_flatten_localized(item['exposureStateDisplay'])}"
    ).lower()

    probe = _as_dict(item.get("probe")) or {}
    probed_at = _as_str(probe.get("probedAt"))
    if probed_at:
        meta_lines = [str(value) for value in item.get("metaLines", []) if str(value).strip()]
        meta_lines.append(f"Last probe: {probed_at}")
        item["metaLines"] = meta_lines
    return item


def _build_overview(
    *,
    items: list[dict[str, object]],
    config_data: dict[str, object],
    tool_observability: dict[str, object],
    configured_bundles: list[str],
    selected_tool_names: list[str],
) -> dict[str, object]:
    builtin_count = sum(1 for item in items if item.get("kind") == "builtin")
    server_count = sum(1 for item in items if item.get("kind") == "mcp_server")
    attention_count = sum(1 for item in items if bool(item.get("needsAttention")))
    available_count = sum(
        1
        for item in items
        if item.get("kind") == "builtin" and item.get("runtimeState") == "available"
    )
    healthy_mcp_count = sum(
        1 for item in items if item.get("kind") == "mcp_server" and item.get("status") == "healthy"
    )
    tools_cfg = _as_dict(_get_path(config_data, "tools", {})) or {}
    exposure = _as_dict(tools_cfg.get("toolExposure")) or {}
    summary_metrics = [
        {
            "key": "available",
            "displayLabel": _localized("当前可用", "Available now"),
            "value": available_count,
            "tone": "#F97316",
        },
        {
            "key": "recent_exposure",
            "displayLabel": _localized("最近暴露", "Exposed recently"),
            "value": len(selected_tool_names),
            "tone": "#34D399",
        },
        {
            "key": "mcp_connected",
            "displayLabel": _localized("MCP 已连通", "MCP connected"),
            "value": healthy_mcp_count,
            "tone": "#60A5FA",
        },
        {
            "key": "attention",
            "displayLabel": _localized("需处理", "Needs attention"),
            "value": attention_count,
            "tone": "#EF4444",
        },
    ]
    return {
        "builtinCount": builtin_count,
        "mcpServerCount": server_count,
        "attentionCount": attention_count,
        "runningNowCount": healthy_mcp_count,
        "availableCount": available_count,
        "recentExposureCount": len(selected_tool_names),
        "healthyMcpCount": healthy_mcp_count,
        "toolExposureMode": _as_str(exposure.get("mode"), "auto") or "auto",
        "toolExposureBundles": configured_bundles,
        "restrictToWorkspace": bool(tools_cfg.get("restrictToWorkspace")),
        "desktopEnabled": bool(_get_path(config_data, "tools.desktop.enabled", True)),
        "summaryMetrics": summary_metrics,
        "exposureBundleOptions": [
            {"key": bundle, "displayLabel": _localized_label(_BUNDLE_LABELS, bundle)}
            for bundle in _DEFAULT_BUNDLES
        ],
        "observability": _observability_summary(tool_observability),
    }


def _runtime_state(item: dict[str, object]) -> str:
    status = _as_str(item.get("status"))
    if status in {"healthy", "ready", "limited"}:
        return "available"
    if status == "configured":
        return "configured_only"
    if status in {"disabled", "needs_setup", "blocked", "error", "unavailable"}:
        return status
    return "unknown"


def _runtime_state_display(item: dict[str, object]) -> dict[str, str]:
    return _localized_label(_RUNTIME_STATE_LABELS, _runtime_state(item))


def _exposure_state(
    *,
    item: dict[str, object],
    enabled_bundles: set[str],
    selected_bundles: set[str],
    matched_tools: list[str],
    has_recent_run: bool,
) -> str:
    if matched_tools:
        return "exposed_last_run"
    if item.get("kind") == "builtin":
        bundle = _as_str(item.get("bundle")).lower()
        if bundle and bundle not in enabled_bundles:
            return "bundle_disabled"
        if has_recent_run and bundle and bundle in selected_bundles:
            return "eligible_not_selected"
        return "no_recent_run"
    if has_recent_run and _normalize_list(item.get("includedTools")):
        return "eligible_not_selected"
    return "no_recent_run"


def _attention_copy(item: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    kind = _as_str(item.get("kind"))
    status = _as_str(item.get("status"))
    form_kind = _as_str(item.get("formKind"))
    config_values = _config_values(item)

    if kind == "mcp_server":
        if status == "needs_setup":
            return (
                _localized("还没有可测试的 MCP 定义。", "This MCP server is missing the fields required to test."),
                _localized("补充 command 或 URL。", "Add a command or URL."),
            )
        if status == "configured":
            return (
                _localized("定义已保存，但还没有最近一次握手结果。", "The server is saved, but it has not been probed yet."),
                _localized("运行一次连接测试。", "Run a connection test."),
            )
        if status == "error":
            return (
                _localized("最近一次握手失败。", "The latest MCP probe failed."),
                _localized("修正配置或运行环境后重新测试。", "Fix the config or environment, then test again."),
            )
        return _empty_localized(), _empty_localized()

    if form_kind == "desktop":
        missing = _normalize_list(config_values.get("missingDependencies"))
        if status == "blocked" and missing:
            joined = ", ".join(missing)
            return (
                _localized(f"缺少依赖：{joined}。", f"Missing dependencies: {joined}."),
                _localized("安装桌面自动化依赖后重试。", "Install the desktop automation dependencies, then try again."),
            )
        if status == "disabled":
            return (
                _localized("桌面自动化当前处于关闭状态。", "Desktop automation is currently disabled."),
                _localized("开启桌面自动化开关。", "Enable desktop automation."),
            )
    if form_kind == "coding":
        backend_errors = _normalize_list(config_values.get("backendErrors"))
        if status == "blocked" and backend_errors:
            return (
                _localized("检测到后端命令，但初始化失败。", "A backend command was found, but initialization failed."),
                _localized("检查对应 CLI 与 Python 依赖。", "Check the backend CLI and Python dependencies."),
            )
        if status == "unavailable":
            return (
                _localized("还没有可用的编程后端。", "No coding backend is available yet."),
                _localized("安装 OpenCode、Codex 或 Claude Code。", "Install OpenCode, Codex, or Claude Code."),
            )
    if form_kind == "web" and status == "limited":
        browser_enabled = bool(config_values.get("browserEnabled"))
        browser_available = bool(config_values.get("browserAvailable"))
        has_search = bool(
            config_values.get("braveApiKey")
            or config_values.get("tavilyApiKey")
            or config_values.get("exaApiKey")
        )
        if browser_enabled and not browser_available:
            return (
                _localized("浏览器 runtime 还没准备好。", "The browser runtime is not ready yet."),
                _localized("补齐托管浏览器 runtime，或关闭浏览器自动化。", "Install the managed browser runtime or disable browser automation."),
            )
        if not has_search:
            return (
                _localized("当前只有抓取能力，没有联网搜索。", "Fetch is available, but live search is not configured."),
                _localized("配置一个网页搜索 provider key。", "Configure a web search provider key."),
            )
    if form_kind in {"embedding", "image_generation"} and status == "needs_setup":
        return (
            _localized("这组能力还缺少模型或凭据。", "This capability still needs a model or credentials."),
            _localized("补齐模型与 API Key。", "Fill in the model and API key."),
        )
    return _empty_localized(), _empty_localized()


def _includes_summary(item: dict[str, object]) -> dict[str, str]:
    count = len(_normalize_list(item.get("includedTools")))
    if item.get("kind") == "mcp_server":
        if count <= 0:
            return _localized(
                "先测试连接，Bao 才知道这个 server 暴露了哪些工具。",
                "Run a probe first so Bao can discover which tools this server exposes.",
            )
        return _localized(
            f"最近一次探测发现 {count} 个运行时工具。",
            f"The latest probe found {count} runtime tools.",
        )
    if count <= 0:
        return _localized(
            "这个能力族没有单独的用户侧配置入口。",
            "This capability family does not expose separate end-user configuration.",
        )
    return _localized(
        f"包含 {count} 个底层工具。",
        f"Includes {count} underlying tools.",
    )


def _exposure_summary(
    item: dict[str, object], exposure_state: str, matched_tools: list[str]
) -> dict[str, str]:
    if exposure_state == "exposed_last_run":
        visible = ", ".join(matched_tools[:3])
        overflow = len(matched_tools) - min(len(matched_tools), 3)
        suffix = f" (+{overflow})" if overflow > 0 else ""
        return _localized(
            f"最近一次运行已暴露：{visible}{suffix}",
            f"Exposed in the latest run: {visible}{suffix}",
        )
    if exposure_state == "bundle_disabled":
        return _localized(
            "这组能力当前没有参与自动暴露。",
            "This bundle is currently excluded from auto exposure.",
        )
    if exposure_state == "eligible_not_selected":
        return _localized(
            "最近一次运行里，这组能力没有被选中。",
            "This capability was eligible, but not selected in the latest run.",
        )
    return _localized(
        "还没有最近一次运行记录。",
        "There is no recent tool exposure record yet.",
    )


def _badge_items(item: dict[str, object], exposure_state: str) -> list[dict[str, str]]:
    status = _as_str(item.get("status"))
    badges: list[dict[str, str]] = []
    status_text = _flatten_localized(item.get("displayStatusLabel"))
    if status_text:
        badges.append({"text": status_text, "tone": _STATUS_TONES.get(status, "#A1A1AA")})
    exposure_text = _flatten_localized(_localized_label(_EXPOSURE_LABELS, exposure_state))
    if exposure_state in {"exposed_last_run", "bundle_disabled"} and exposure_text:
        badges.append(
            {
                "text": exposure_text,
                "tone": "#34D399" if exposure_state == "exposed_last_run" else "#F59E0B",
            }
        )
    if item.get("kind") == "builtin":
        bundle_text = _flatten_localized(item.get("displayBundleLabel"))
        if bundle_text:
            badges.append({"text": bundle_text, "tone": "#60A5FA"})
    else:
        transport = _as_str(_config_values(item).get("transport")).upper()
        if transport:
            badges.append({"text": transport, "tone": "#60A5FA"})
    return badges


def _observability_summary(tool_observability: dict[str, object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, label_pair in _OBSERVABILITY_FIELDS:
        value = tool_observability.get(key)
        if value is None:
            continue
        text = f"{value:.2f}" if isinstance(value, float) else str(value)
        items.append({"label": _flatten_localized(_localized(*label_pair)), "value": text})
    return items


def _configured_bundles(config_data: dict[str, object]) -> list[str]:
    bundles = _normalize_list(_get_path(config_data, "tools.toolExposure.bundles", []))
    if not bundles:
        return list(_DEFAULT_BUNDLES)
    return [bundle for bundle in bundles if bundle in _DEFAULT_BUNDLES]


def _tool_observability_from_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    observability = _as_dict(snapshot.get("tool_observability"))
    if observability is not None:
        return dict(observability)
    return dict(snapshot)


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


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    return None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return value
    return None


def _as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def _get_path(data: dict[str, object], dotpath: str, default: object = None) -> object:
    node: object = data
    for part in dotpath.split("."):
        current = _as_dict(node)
        if current is None or part not in current:
            return default
        node = current[part]
    return node


def _normalize_list(value: object) -> list[str]:
    return [str(item) for item in (_as_list(value) or []) if str(item).strip()]


def _config_values(item: dict[str, object]) -> dict[str, object]:
    return _as_dict(item.get("configValues")) or {}


def _localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def _empty_localized() -> dict[str, str]:
    return _localized("", "")


def _localized_label(labels: dict[str, tuple[str, str]], key: str) -> dict[str, str]:
    zh, en = labels.get(key, (key, key))
    return _localized(zh, en)


def _flatten_localized(value: object) -> str:
    data = _as_dict(value)
    if data is None:
        return _as_str(value)
    return _as_str(data.get("zh")) or _as_str(data.get("en"))
