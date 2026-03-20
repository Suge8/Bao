from __future__ import annotations

from dataclasses import dataclass

from bao.agent._capability_registry_common import (
    _CAPABILITY_LABELS,
    _EXPOSURE_LABELS,
    _RUNTIME_STATE_LABELS,
    _STATUS_LABELS,
    _STATUS_TONES,
    as_dict,
    as_str,
    config_values,
    empty_localized,
    flatten_localized,
    localized,
    localized_label,
    normalize_list,
)
from bao.agent._tool_exposure_domains import (
    TOOL_EXPOSURE_DOMAIN_LABELS as _DOMAIN_LABELS,
)
from bao.agent._tool_exposure_domains import item_domains_for_tools


@dataclass(frozen=True)
class DecorateItemRequest:
    item: dict[str, object]
    enabled_domains: set[str]
    selected_domains: set[str]
    selected_tool_names: set[str]
    has_recent_run: bool


@dataclass(frozen=True)
class ExposureStateRequest:
    item: dict[str, object]
    enabled_domains: set[str]
    selected_domains: set[str]
    matched_tools: list[str]
    has_recent_run: bool


def decorate_item(request: DecorateItemRequest) -> dict[str, object]:
    item = request.item
    capabilities = normalize_list(item.get("capabilities"))
    item["displayCapabilities"] = [localized_label(_CAPABILITY_LABELS, value) for value in capabilities]
    item_domains = item_domains_for_tools(normalize_list(item.get("includedTools")))
    item["displayDomainLabels"] = [localized_label(_DOMAIN_LABELS, value) for value in sorted(item_domains)]
    item["displayStatusLabel"] = localized_label(_STATUS_LABELS, as_str(item.get("status")))
    item["runtimeState"] = runtime_state(item)
    item["runtimeStateDisplay"] = localized_label(_RUNTIME_STATE_LABELS, item["runtimeState"])
    included_tools = normalize_list(item.get("includedTools"))
    matched_tools = [name for name in included_tools if name in request.selected_tool_names]
    exposure_state = resolve_exposure_state(
        ExposureStateRequest(
            item=item,
            enabled_domains=request.enabled_domains,
            selected_domains=request.selected_domains,
            matched_tools=matched_tools,
            has_recent_run=request.has_recent_run,
        )
    )
    item["exposureState"] = exposure_state
    item["exposureStateDisplay"] = localized_label(_EXPOSURE_LABELS, exposure_state)
    item["recentExposureTools"] = matched_tools
    item["exposureSummaryDisplay"] = exposure_summary(exposure_state, matched_tools)
    item["attentionReasonDisplay"], item["attentionActionDisplay"] = attention_copy(item)
    item["includesSummaryDisplay"] = includes_summary(item)
    item["badges"] = badge_items(item, exposure_state)
    item["searchText"] = (
        f"{item.get('searchText', '')} "
        f"{flatten_localized(item['displayStatusLabel'])} "
        f"{flatten_localized(item['runtimeStateDisplay'])} "
        f"{flatten_localized(item['exposureStateDisplay'])}"
    ).lower()
    probe = as_dict(item.get("probe")) or {}
    probed_at = as_str(probe.get("probedAt"))
    if probed_at:
        meta_lines = [str(value) for value in item.get("metaLines", []) if str(value).strip()]
        item["metaLines"] = [*meta_lines, f"Last probe: {probed_at}"]
    return item


def runtime_state(item: dict[str, object]) -> str:
    status = as_str(item.get("status"))
    if status in {"healthy", "ready", "limited"}:
        return "available"
    if status == "configured":
        return "configured_only"
    if status in {"disabled", "needs_setup", "blocked", "error", "unavailable"}:
        return status
    return "unknown"


def resolve_exposure_state(request: ExposureStateRequest) -> str:
    if request.matched_tools:
        return "exposed_last_run"
    item = request.item
    if item.get("kind") != "builtin":
        if request.has_recent_run and normalize_list(item.get("includedTools")):
            return "eligible_not_selected"
        return "no_recent_run"
    item_domains = item_domains_for_tools(normalize_list(item.get("includedTools")))
    if item_domains and item_domains.isdisjoint(request.enabled_domains):
        return "domain_disabled"
    if request.has_recent_run and item_domains & request.selected_domains:
        return "eligible_not_selected"
    return "no_recent_run"


def attention_copy(item: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    if item.get("kind") == "mcp_server":
        return _mcp_attention_copy(as_str(item.get("status")))
    form_kind = as_str(item.get("formKind"))
    status = as_str(item.get("status"))
    if form_kind == "desktop":
        return _desktop_attention_copy(status, config_values(item))
    if form_kind == "coding":
        return _coding_attention_copy(status, config_values(item))
    if form_kind == "web" and status == "limited":
        return _web_attention_copy(config_values(item))
    if form_kind in {"embedding", "image_generation"} and status == "needs_setup":
        return (
            localized("这组能力还缺少模型或凭据。", "This capability still needs a model or credentials."),
            localized("补齐模型与 API Key。", "Fill in the model and API key."),
        )
    return empty_localized(), empty_localized()


def _mcp_attention_copy(status: str) -> tuple[dict[str, str], dict[str, str]]:
    if status == "needs_setup":
        return localized("还没有可测试的 MCP 定义。", "This MCP server is missing the fields required to test."), localized("补充 command 或 URL。", "Add a command or URL.")
    if status == "configured":
        return localized("定义已保存，但还没有最近一次握手结果。", "The server is saved, but it has not been probed yet."), localized("运行一次连接测试。", "Run a connection test.")
    if status == "error":
        return localized("最近一次握手失败。", "The latest MCP probe failed."), localized("修正配置或运行环境后重新测试。", "Fix the config or environment, then test again.")
    return empty_localized(), empty_localized()


def _desktop_attention_copy(status: str, values: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    missing = normalize_list(values.get("missingDependencies"))
    if status == "blocked" and missing:
        joined = ", ".join(missing)
        return localized(f"缺少依赖：{joined}。", f"Missing dependencies: {joined}."), localized("安装桌面自动化依赖后重试。", "Install the desktop automation dependencies, then try again.")
    if status == "disabled":
        return localized("桌面自动化当前处于关闭状态。", "Desktop automation is currently disabled."), localized("开启桌面自动化开关。", "Enable desktop automation.")
    return empty_localized(), empty_localized()


def _coding_attention_copy(status: str, values: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    backend_errors = normalize_list(values.get("backendErrors"))
    if status == "blocked" and backend_errors:
        return localized("检测到后端命令，但初始化失败。", "A backend command was found, but initialization failed."), localized("检查对应 CLI 与 Python 依赖。", "Check the backend CLI and Python dependencies.")
    if status == "unavailable":
        return localized("还没有可用的编程后端。", "No coding backend is available yet."), localized("安装 OpenCode、Codex 或 Claude Code。", "Install OpenCode, Codex, or Claude Code.")
    return empty_localized(), empty_localized()


def _web_attention_copy(values: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    if bool(values.get("browserEnabled")) and not bool(values.get("browserAvailable")):
        return localized("浏览器 runtime 还没准备好。", "The browser runtime is not ready yet."), localized("补齐托管浏览器 runtime，或关闭浏览器自动化。", "Install the managed browser runtime or disable browser automation.")
    has_search = bool(values.get("braveApiKey") or values.get("tavilyApiKey") or values.get("exaApiKey"))
    if not has_search:
        return localized("当前只有抓取能力，没有联网搜索。", "Fetch is available, but live search is not configured."), localized("配置一个网页搜索 provider key。", "Configure a web search provider key.")
    return empty_localized(), empty_localized()


def includes_summary(item: dict[str, object]) -> dict[str, str]:
    count = len(normalize_list(item.get("includedTools")))
    if item.get("kind") == "mcp_server":
        return localized(
            "先测试连接，Bao 才知道这个 server 暴露了哪些工具。",
            "Run a probe first so Bao can discover which tools this server exposes.",
        ) if count <= 0 else localized(
            f"最近一次探测发现 {count} 个运行时工具。",
            f"The latest probe found {count} runtime tools.",
        )
    return localized(
        "这个能力族没有单独的用户侧配置入口。",
        "This capability family does not expose separate end-user configuration.",
    ) if count <= 0 else localized(
        f"包含 {count} 个底层工具。",
        f"Includes {count} underlying tools.",
    )


def exposure_summary(exposure_state: str, matched_tools: list[str]) -> dict[str, str]:
    if exposure_state == "exposed_last_run":
        visible = ", ".join(matched_tools[:3])
        overflow = len(matched_tools) - min(len(matched_tools), 3)
        suffix = f" (+{overflow})" if overflow > 0 else ""
        return localized(f"最近一次运行已暴露：{visible}{suffix}", f"Exposed in the latest run: {visible}{suffix}")
    if exposure_state == "domain_disabled":
        return localized("这组能力当前没有参与自动暴露。", "This domain is currently excluded from auto exposure.")
    if exposure_state == "eligible_not_selected":
        return localized("最近一次运行里，这组能力没有被选中。", "This capability was eligible, but not selected in the latest run.")
    return localized("还没有最近一次运行记录。", "There is no recent tool exposure record yet.")


def badge_items(item: dict[str, object], exposure_state: str) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    status = as_str(item.get("status"))
    status_text = flatten_localized(item.get("displayStatusLabel"))
    if status_text:
        badges.append({"text": status_text, "tone": _STATUS_TONES.get(status, "#A1A1AA")})
    exposure_text = flatten_localized(localized_label(_EXPOSURE_LABELS, exposure_state))
    if exposure_state in {"exposed_last_run", "domain_disabled"} and exposure_text:
        badges.append({"text": exposure_text, "tone": "#34D399" if exposure_state == "exposed_last_run" else "#F59E0B"})
    if item.get("kind") == "builtin":
        for label in item.get("displayDomainLabels", [])[:2]:
            domain_text = flatten_localized(label)
            if domain_text:
                badges.append({"text": domain_text, "tone": "#60A5FA"})
    else:
        transport = as_str(config_values(item).get("transport")).upper()
        if transport:
            badges.append({"text": transport, "tone": "#60A5FA"})
    return badges
