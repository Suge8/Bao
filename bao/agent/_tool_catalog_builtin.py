from __future__ import annotations

from typing import Callable

from bao.agent._tool_catalog_common import (
    BuiltinToolFamily,
    as_str,
    attention_status,
    coding_backends,
    desktop_missing_dependencies,
    get_path,
    localized,
    non_bool_int,
)


def build_builtin_item(
    spec: BuiltinToolFamily,
    config_data: dict[str, object],
    *,
    browser_state_fn: Callable[..., object],
) -> dict[str, object]:
    status, status_label, status_detail, status_detail_display, config_values, meta_lines = _form_payload(
        spec,
        config_data,
        browser_state_fn=browser_state_fn,
    )
    return {
        "id": f"builtin:{spec.id}",
        "kind": "builtin",
        "source": "builtin",
        "name": spec.name,
        "displayName": localized(spec.name_zh, spec.name),
        "bundle": spec.bundle,
        "summary": spec.summary,
        "displaySummary": localized(spec.summary_zh, spec.summary),
        "detail": spec.detail,
        "displayDetail": localized(spec.detail_zh, spec.detail),
        "capabilities": list(spec.capabilities),
        "includedTools": list(spec.included_tools),
        "status": status,
        "statusLabel": status_label,
        "statusDetail": status_detail,
        "statusDetailDisplay": status_detail_display,
        "needsAttention": attention_status(status),
        "formKind": spec.form_kind,
        "configPaths": list(spec.config_paths),
        "configValues": config_values,
        "metaLines": meta_lines,
        "iconSource": spec.icon_source,
        "searchText": " ".join(
            [
                spec.name,
                spec.name_zh,
                spec.summary,
                spec.summary_zh,
                spec.detail,
                spec.detail_zh,
                spec.bundle,
                *spec.capabilities,
                *spec.included_tools,
            ]
        ).lower(),
    }


def _form_payload(
    spec: BuiltinToolFamily,
    config_data: dict[str, object],
    *,
    browser_state_fn: Callable[..., object],
) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    if spec.form_kind == "exec":
        return _exec_payload(config_data)
    if spec.form_kind == "web":
        return _web_payload(config_data, browser_state_fn=browser_state_fn)
    if spec.form_kind == "embedding":
        return _embedding_payload(config_data)
    if spec.form_kind == "image_generation":
        return _image_generation_payload(config_data)
    if spec.form_kind == "desktop":
        return _desktop_payload(config_data)
    if spec.form_kind == "coding":
        return _coding_payload()
    return _overview_payload(spec)


def _exec_payload(config_data: dict[str, object]) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    sandbox_mode = as_str(get_path(config_data, "tools.exec.sandboxMode", "semi-auto"))
    restrict_to_workspace = bool(get_path(config_data, "tools.restrictToWorkspace", False))
    config_values = {
        "timeout": non_bool_int(get_path(config_data, "tools.exec.timeout", 60), 60),
        "pathAppend": as_str(get_path(config_data, "tools.exec.pathAppend", "")),
        "sandboxMode": sandbox_mode or "semi-auto",
        "restrictToWorkspace": restrict_to_workspace,
    }
    return (
        "configured",
        "Workspace only" if restrict_to_workspace else "Configured",
        f"Sandbox {sandbox_mode}",
        localized("命令执行受沙箱和工作区边界约束。", "Command execution is governed by sandbox and workspace boundaries."),
        config_values,
        [f"Sandbox: {sandbox_mode or 'semi-auto'}"],
    )


def _web_payload(
    config_data: dict[str, object],
    *,
    browser_state_fn: Callable[..., object],
) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    provider = as_str(get_path(config_data, "tools.web.search.provider", ""))
    brave = as_str(get_path(config_data, "tools.web.search.braveApiKey", ""))
    tavily = as_str(get_path(config_data, "tools.web.search.tavilyApiKey", ""))
    exa = as_str(get_path(config_data, "tools.web.search.exaApiKey", ""))
    browser_enabled = bool(get_path(config_data, "tools.web.browser.enabled", True))
    browser_state = browser_state_fn(enabled=browser_enabled)
    search_config = {
        "provider": provider,
        "braveApiKey": brave,
        "tavilyApiKey": tavily,
        "exaApiKey": exa,
        "browserEnabled": browser_enabled,
    }
    status, label, detail, display = _resolve_web_status(search_config, browser_state)
    config_values = _web_config_values(config_data, search_config, browser_state)
    meta_lines = [
        f"Search provider: {provider or 'auto'}",
        f"Managed browser: {'ready' if browser_state.available else browser_state.reason}",
    ]
    return status, label, detail, display, config_values, meta_lines


def _resolve_web_status(
    search_config: dict[str, object],
    browser_state: object,
) -> tuple[str, str, str, dict[str, str]]:
    enabled_search = any(
        bool(search_config.get(key))
        for key in ("braveApiKey", "tavilyApiKey", "exaApiKey")
    )
    provider = str(search_config.get("provider") or "")
    if enabled_search and browser_state.available:
        return "ready", "Search + browser", "Search provider and managed browser runtime are ready.", localized("网页搜索 provider 和托管浏览器 runtime 都已就绪。", "Search provider and managed browser runtime are ready.")
    if enabled_search:
        return "ready", "Search ready", provider or "Provider auto-select", localized("网页搜索 provider 已配置。", "A web search provider is configured.")
    if browser_state.available:
        return "limited", "Fetch + browser", "Direct fetch and managed browser automation are available.", localized("当前可直接抓取网页，也可使用托管浏览器自动化。", "Direct fetch and managed browser automation are available.")
    if bool(search_config.get("browserEnabled")) and browser_state.reason != "disabled":
        return "limited", "Fetch only", browser_state.detail, localized("当前只有直接抓取可用；浏览器 runtime 尚未就绪。", "Fetch is available, but the managed browser runtime is not ready yet.")
    return "limited", "Fetch only", "Add a search provider key to enable fresh search.", localized("当前只有抓取能力可用；若要启用联网搜索，请配置 provider key。", "Fetch is available, but live search still needs a provider key.")


def _web_config_values(
    config_data: dict[str, object],
    search_config: dict[str, object],
    browser_state: object,
) -> dict[str, object]:
    return {
        "provider": search_config["provider"],
        "braveApiKey": search_config["braveApiKey"],
        "tavilyApiKey": search_config["tavilyApiKey"],
        "exaApiKey": search_config["exaApiKey"],
        "maxResults": non_bool_int(get_path(config_data, "tools.web.search.maxResults", 5), 5),
        "browserEnabled": search_config["browserEnabled"],
        "browserAvailable": browser_state.available,
        "browserRuntimeReady": browser_state.runtime_ready,
        "browserRuntimeSource": browser_state.runtime_source,
        "browserRuntimeRoot": browser_state.runtime_root,
        "browserProfilePath": browser_state.profile_path,
        "browserStatusReason": browser_state.reason,
        "browserStatusDetail": browser_state.detail,
        "agentBrowserHomePath": browser_state.agent_browser_home_path,
        "agentBrowserPath": browser_state.agent_browser_path,
        "browserExecutablePath": browser_state.browser_executable_path,
    }


def _embedding_payload(config_data: dict[str, object]) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    model = as_str(get_path(config_data, "tools.embedding.model", ""))
    api_key = as_str(get_path(config_data, "tools.embedding.apiKey", ""))
    enabled = bool(model and api_key)
    config_values = {
        "model": model,
        "apiKey": api_key,
        "baseUrl": as_str(get_path(config_data, "tools.embedding.baseUrl", "")),
        "dim": non_bool_int(get_path(config_data, "tools.embedding.dim", 0), 0),
    }
    return (
        "ready" if enabled else "needs_setup",
        "Configured" if enabled else "Needs setup",
        model or "Add a model and API key to enable embeddings.",
        localized(
            "Embedding 模型与密钥已配置。" if enabled else "配置模型和 API Key 后，语义检索才会启用。",
            "Embedding model and key are configured."
            if enabled
            else "Configure a model and API key to enable semantic retrieval.",
        ),
        config_values,
        [f"Model: {model or 'none'}"],
    )


def _image_generation_payload(config_data: dict[str, object]) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    model = as_str(get_path(config_data, "tools.imageGeneration.model", ""))
    api_key = as_str(get_path(config_data, "tools.imageGeneration.apiKey", ""))
    enabled = bool(api_key)
    config_values = {
        "apiKey": api_key,
        "model": model,
        "baseUrl": as_str(get_path(config_data, "tools.imageGeneration.baseUrl", "")),
    }
    return (
        "ready" if enabled else "needs_setup",
        "Configured" if enabled else "Needs setup",
        model or "Configure an API key to enable image generation.",
        localized(
            "图像生成模型已可用。" if enabled else "配置图像模型或 API Key 后才会启用。",
            "Image generation is configured."
            if enabled
            else "Configure a model or API key to enable image generation.",
        ),
        config_values,
        [f"Model: {model or 'default'}"],
    )


def _desktop_payload(config_data: dict[str, object]) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    enabled = bool(get_path(config_data, "tools.desktop.enabled", True))
    missing_dependencies = desktop_missing_dependencies() if enabled else []
    config_values = {"enabled": enabled, "missingDependencies": missing_dependencies}
    if not enabled:
        return "disabled", "Disabled", "Enable desktop automation before Bao can act on the local UI.", localized("本地桌面控制当前关闭。", "Desktop control is currently disabled."), config_values, []
    if missing_dependencies:
        joined = ", ".join(missing_dependencies)
        return "blocked", "Missing dependencies", f"Missing desktop dependencies: {joined}", localized(f"缺少桌面依赖：{joined}。", f"Missing desktop dependencies: {joined}."), config_values, [f"Missing deps: {joined}"]
    return "ready", "Enabled", "Desktop automation is available to the agent.", localized("本地桌面控制已开启。", "Desktop control is enabled."), config_values, []


def _coding_payload() -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    backends, backend_errors = coding_backends()
    config_values = {"backends": backends, "backendErrors": backend_errors}
    meta_lines = []
    if backends:
        detail = ", ".join(backends)
        meta_lines.append(detail)
        return "ready", "Available", detail, localized("已检测到编程后端。", "Coding backends detected."), config_values, meta_lines
    if backend_errors:
        meta_lines.extend(backend_errors[:2])
        return "blocked", "Backend blocked", backend_errors[0], localized("检测到编程命令，但后端初始化失败。", "A coding backend binary was found, but initialization failed."), config_values, meta_lines
    detail = "Install OpenCode, Codex, or Claude Code to activate coding delegation."
    return "unavailable", "No backend", detail, localized("尚未检测到 OpenCode、Codex 或 Claude Code。", "No OpenCode, Codex, or Claude Code backend detected yet."), config_values, meta_lines


def _overview_payload(spec: BuiltinToolFamily) -> tuple[str, str, str, dict[str, str], dict[str, object], list[str]]:
    if spec.id == "cron":
        return "configured", "Runtime-managed", "Available when the hub starts with cron support.", localized("Cron 只有在运行时挂上 hub service 时才会真正可用；这里先展示它的职责边界。", "Available when the hub starts with cron support."), {}, []
    return "ready", "Core", spec.detail, localized(spec.detail_zh, spec.detail), {}, []
