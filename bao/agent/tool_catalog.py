from __future__ import annotations

import shutil
from dataclasses import dataclass

from bao.browser import get_browser_capability_state


@dataclass(frozen=True)
class BuiltinToolFamily:
    id: str
    name: str
    name_zh: str
    bundle: str
    summary: str
    summary_zh: str
    detail: str
    detail_zh: str
    capabilities: tuple[str, ...]
    included_tools: tuple[str, ...]
    icon_source: str
    form_kind: str = "overview"
    config_paths: tuple[str, ...] = ()


def _iconoir(name: str) -> str:
    return f"../resources/icons/vendor/iconoir/{name}.svg"


_BUILTIN_TOOL_FAMILIES: tuple[BuiltinToolFamily, ...] = (
    BuiltinToolFamily(
        id="filesystem",
        name="Local Files",
        name_zh="本地文件",
        bundle="core",
        summary="Read, write, edit, and list workspace files.",
        summary_zh="读取、写入、编辑并列出工作区文件。",
        detail="These tools are the core local file surface for inspecting and changing project files.",
        detail_zh="这是 Bao 的核心本地文件能力，用于查看、创建和修改项目文件。",
        capabilities=("Filesystem", "Workspace", "Authoring"),
        included_tools=("read_file", "write_file", "edit_file", "list_dir"),
        icon_source=_iconoir("book-stack"),
    ),
    BuiltinToolFamily(
        id="exec",
        name="Terminal Exec",
        name_zh="终端执行",
        bundle="core",
        summary="Run shell commands on the runtime host with sandbox controls.",
        summary_zh="在运行主机上执行命令，并受超时与沙箱策略约束。",
        detail="Exec is the bridge to local shell workflows. Its scope is shaped by timeout, sandbox mode, and workspace restrictions.",
        detail_zh="Exec 是本机命令桥。你可以在这里控制超时、PATH 追加、沙箱模式与工作区边界。",
        capabilities=("Shell", "Local host", "Diagnostics"),
        included_tools=("exec",),
        icon_source=_iconoir("computer"),
        form_kind="exec",
        config_paths=(
            "tools.exec.timeout",
            "tools.exec.pathAppend",
            "tools.exec.sandboxMode",
            "tools.restrictToWorkspace",
        ),
    ),
    BuiltinToolFamily(
        id="coding",
        name="Coding Agent",
        name_zh="编程代理",
        bundle="code",
        summary="Delegate multi-file coding and debugging to external coding backends.",
        summary_zh="把多文件实现、调试与重构委派给已安装的编程后端。",
        detail="Coding Agent routes heavier implementation work to installed coding backends such as OpenCode, Codex, or Claude Code.",
        detail_zh="编程代理把高复杂度实现委派给 OpenCode、Codex 或 Claude Code 等后端；这里主要展示当前可用后端。",
        capabilities=("Codegen", "Refactor", "Debug"),
        included_tools=("coding_agent", "coding_agent_details"),
        icon_source="../resources/icons/sidebar-subagent.svg",
        form_kind="coding",
    ),
    BuiltinToolFamily(
        id="web",
        name="Web Retrieval",
        name_zh="网页检索",
        bundle="web",
        summary="Search the web, fetch URLs, and automate browser flows.",
        summary_zh="搜索网页、抓取 URL，并在需要时驱动浏览器。",
        detail="This family combines web search, direct fetch, and browser automation. Search quality depends on configured providers.",
        detail_zh="网页检索把搜索 provider、URL 抓取和浏览器操作聚合在同一工具族里；搜索质量取决于你配置的 provider key。",
        capabilities=("Search", "Fetch", "Browser"),
        included_tools=("web_search", "web_fetch", "agent_browser"),
        icon_source=_iconoir("page-search"),
        form_kind="web",
        config_paths=(
            "tools.web.search.provider",
            "tools.web.search.tavilyApiKey",
            "tools.web.search.braveApiKey",
            "tools.web.search.exaApiKey",
            "tools.web.search.maxResults",
            "tools.web.browser.enabled",
        ),
    ),
    BuiltinToolFamily(
        id="embedding",
        name="Embeddings",
        name_zh="向量嵌入",
        bundle="core",
        summary="Provide semantic embeddings for memory and retrieval workflows.",
        summary_zh="为语义检索与长期记忆提供向量嵌入。",
        detail="Embedding settings back semantic search and long-term memory quality. They stay dormant until a model and API key are configured.",
        detail_zh="Embedding 设置会直接影响语义检索与记忆质量。只有模型与 API Key 都配置好时，它才会真正启用。",
        capabilities=("Embeddings", "Retrieval", "Memory"),
        included_tools=("embedding_runtime",),
        icon_source=_iconoir("database-settings"),
        form_kind="embedding",
        config_paths=(
            "tools.embedding.model",
            "tools.embedding.apiKey",
            "tools.embedding.baseUrl",
            "tools.embedding.dim",
        ),
    ),
    BuiltinToolFamily(
        id="image_generation",
        name="Image Generation",
        name_zh="图像生成",
        bundle="core",
        summary="Create images from prompts when an image model is configured.",
        summary_zh="配置图像生成模型后即可从提示词产图。",
        detail="Image generation is optional and only becomes active once a provider key is configured.",
        detail_zh="图像生成是可选能力。配置好 API Key 之后，Bao 才会把它当作可调用工具。",
        capabilities=("Image", "Creative", "Generation"),
        included_tools=("image_generation",),
        icon_source=_iconoir("circle-spark"),
        form_kind="image_generation",
        config_paths=(
            "tools.imageGeneration.apiKey",
            "tools.imageGeneration.model",
            "tools.imageGeneration.baseUrl",
        ),
    ),
    BuiltinToolFamily(
        id="memory",
        name="Memory Controls",
        name_zh="记忆控制",
        bundle="core",
        summary="Write, update, and remove explicit long-term memory entries.",
        summary_zh="显式写入、更新和删除长期记忆。",
        detail="These tools let Bao persist explicit facts into the long-term memory system without opening the memory workspace manually.",
        detail_zh="这组工具负责显式修改长期记忆；更细的查看与整理仍建议在记忆工作台完成。",
        capabilities=("Memory", "Persistence", "Curation"),
        included_tools=("remember", "forget", "update_memory"),
        icon_source="../resources/icons/sidebar-memory.svg",
    ),
    BuiltinToolFamily(
        id="planning_subagents",
        name="Planning and Subagents",
        name_zh="计划与子代理",
        bundle="core",
        summary="Create plans and delegate longer tasks to subagents.",
        summary_zh="管理计划步骤，并把长任务委派给子代理。",
        detail="This family covers linear planning, background subagent work, progress inspection, and task cancellation.",
        detail_zh="计划与子代理属于执行编排层：创建计划、推进步骤、委派任务、追踪进度和取消任务都在这里。",
        capabilities=("Plan", "Delegate", "Track"),
        included_tools=(
            "create_plan",
            "update_plan_step",
            "clear_plan",
            "spawn",
            "check_tasks",
            "cancel_task",
            "check_tasks_json",
        ),
        icon_source="../resources/icons/sidebar-subagent.svg",
    ),
    BuiltinToolFamily(
        id="message_diagnostics",
        name="Messaging and Diagnostics",
        name_zh="消息与诊断",
        bundle="core",
        summary="Send cross-channel messages and inspect runtime diagnostics.",
        summary_zh="跨渠道发消息，并查看运行诊断。",
        detail="These tools cover explicit outbound delivery and structured internal diagnostics for framework-side failures.",
        detail_zh="消息与诊断把跨渠道发送和框架内部诊断放在一起，用于支持类与排障类任务。",
        capabilities=("Messaging", "Diagnostics", "Support"),
        included_tools=("message", "runtime_diagnostics"),
        icon_source=_iconoir("message-alert"),
    ),
    BuiltinToolFamily(
        id="cron",
        name="Scheduled Tasks",
        name_zh="定时任务",
        bundle="core",
        summary="Schedule reminders and recurring workflows.",
        summary_zh="配置提醒和周期任务。",
        detail="Cron is active when the runtime includes the cron service and lets Bao manage scheduled reminders and routines.",
        detail_zh="Cron 只有在运行时挂上 cron service 时才会真正可用；这里先展示它的职责边界。",
        capabilities=("Schedule", "Reminder", "Automation"),
        included_tools=("cron",),
        icon_source=_iconoir("calendar-rotate"),
    ),
    BuiltinToolFamily(
        id="desktop",
        name="Desktop Automation",
        name_zh="桌面自动化",
        bundle="desktop",
        summary="See and control the local desktop with screenshots and input actions.",
        summary_zh="截图、点击、输入并控制本地桌面。",
        detail="Desktop automation is powerful and high-risk. It should stay explicit, visible, and easy to disable.",
        detail_zh="桌面自动化是高权限能力，所以它的控制面应当清晰、直接、容易关闭。",
        capabilities=("Desktop", "Input", "Visual"),
        included_tools=(
            "screenshot",
            "click",
            "type_text",
            "key_press",
            "scroll",
            "drag",
            "get_screen_info",
        ),
        icon_source=_iconoir("computer"),
        form_kind="desktop",
        config_paths=("tools.desktop.enabled",),
    ),
)


def _localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


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


def _non_bool_int(value: object, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
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


def _attention_status(status: str) -> bool:
    return status in {"limited", "disabled", "needs_setup", "error", "unavailable"}


def _coding_backends() -> list[str]:
    backends: list[str] = []
    for name, binary in (("OpenCode", "opencode"), ("Codex", "codex"), ("Claude Code", "claude")):
        if shutil.which(binary):
            backends.append(name)
    return backends


def _mcp_transport(command: str, url: str) -> str:
    if command:
        return "stdio"
    if url:
        return "http"
    return "unconfigured"


def _mcp_status_display(
    *,
    status: str,
    probe_error: str,
    tool_count: int,
) -> dict[str, str]:
    if status == "healthy":
        return _localized(
            f"握手成功，已发现 {tool_count} 个运行时工具",
            f"{tool_count} runtime tools discovered",
        )
    if status == "needs_setup":
        return _localized(
            "补充 command 或 URL 后即可测试。",
            "Add a command or URL, then test the connection.",
        )
    if status == "configured":
        return _localized(
            "定义已保存，建议立即做一次探测。",
            "The definition is saved; run a probe next.",
        )
    if probe_error:
        return _localized(probe_error, probe_error)
    return _localized("最近一次探测失败。", "Probe failed")


def _mcp_status(
    *,
    transport: str,
    probe: dict[str, object],
    tool_count: int,
) -> tuple[str, str, str, dict[str, str]]:
    probe_error = _as_str(probe.get("error"))
    if transport == "unconfigured":
        status = "needs_setup"
        label = "Needs setup"
        detail = "Add either a stdio command or an HTTP URL."
    elif not probe:
        status = "configured"
        label = "Configured"
        detail = "Ready to test"
    elif bool(probe.get("canConnect")):
        status = "healthy"
        label = "Connected"
        detail = f"{tool_count} runtime tools discovered"
    else:
        status = "error"
        label = "Connection failed"
        detail = probe_error or "Probe failed"
    return status, label, detail, _mcp_status_display(
        status=status,
        probe_error=probe_error,
        tool_count=tool_count,
    )


class ToolCatalog:
    def list_items(
        self,
        config_data: dict[str, object],
        probe_results: dict[str, dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        probes = probe_results or {}
        items = [self._build_builtin_item(spec, config_data) for spec in _BUILTIN_TOOL_FAMILIES]
        items.extend(self._build_mcp_server_items(config_data, probes))
        items.sort(key=self._sort_key)
        return items

    def build_overview(
        self,
        items: list[dict[str, object]],
        config_data: dict[str, object],
    ) -> dict[str, object]:
        builtin_count = sum(1 for item in items if item.get("kind") == "builtin")
        server_count = sum(1 for item in items if item.get("kind") == "mcp_server")
        attention_count = sum(1 for item in items if bool(item.get("needsAttention")))
        runtime_count = sum(1 for item in items if item.get("status") == "healthy")
        tools_cfg = _as_dict(_get_path(config_data, "tools", {})) or {}
        exposure = _as_dict(tools_cfg.get("toolExposure")) or {}
        bundles = _as_list(exposure.get("bundles")) or []
        return {
            "builtinCount": builtin_count,
            "mcpServerCount": server_count,
            "attentionCount": attention_count,
            "runningNowCount": runtime_count,
            "toolExposureMode": _as_str(exposure.get("mode"), "auto") or "auto",
            "toolExposureBundles": [str(item) for item in bundles],
            "restrictToWorkspace": bool(tools_cfg.get("restrictToWorkspace")),
            "desktopEnabled": bool(_get_path(config_data, "tools.desktop.enabled", True)),
        }

    def _build_builtin_item(
        self, spec: BuiltinToolFamily, config_data: dict[str, object]
    ) -> dict[str, object]:
        status = "ready"
        status_label = "Ready"
        status_detail = spec.summary
        status_detail_display = _localized(spec.summary_zh, spec.summary)
        config_values: dict[str, object] = {}
        meta_lines: list[str] = []

        if spec.form_kind == "exec":
            sandbox_mode = _as_str(_get_path(config_data, "tools.exec.sandboxMode", "semi-auto"))
            restrict_to_workspace = bool(_get_path(config_data, "tools.restrictToWorkspace", False))
            status = "configured"
            status_label = "Workspace only" if restrict_to_workspace else "Configured"
            status_detail = f"Sandbox {sandbox_mode}"
            status_detail_display = _localized(
                "命令执行受沙箱和工作区边界约束。",
                "Command execution is governed by sandbox and workspace boundaries.",
            )
            config_values = {
                "timeout": _non_bool_int(_get_path(config_data, "tools.exec.timeout", 60), 60),
                "pathAppend": _as_str(_get_path(config_data, "tools.exec.pathAppend", "")),
                "sandboxMode": sandbox_mode or "semi-auto",
                "restrictToWorkspace": restrict_to_workspace,
            }
            meta_lines.append(f"Sandbox: {sandbox_mode or 'semi-auto'}")
        elif spec.form_kind == "web":
            provider = _as_str(_get_path(config_data, "tools.web.search.provider", ""))
            brave = _as_str(_get_path(config_data, "tools.web.search.braveApiKey", ""))
            tavily = _as_str(_get_path(config_data, "tools.web.search.tavilyApiKey", ""))
            exa = _as_str(_get_path(config_data, "tools.web.search.exaApiKey", ""))
            enabled_search = bool(brave or tavily or exa)
            browser_enabled = bool(_get_path(config_data, "tools.web.browser.enabled", True))
            browser_state = get_browser_capability_state(enabled=browser_enabled)
            if enabled_search and browser_state.available:
                status = "ready"
                status_label = "Search + browser"
                status_detail = "Search provider and managed browser runtime are ready."
                status_detail_display = _localized(
                    "网页搜索 provider 和托管浏览器 runtime 都已就绪。",
                    "Search provider and managed browser runtime are ready.",
                )
            elif enabled_search:
                status = "ready"
                status_label = "Search ready"
                status_detail = provider or "Provider auto-select"
                status_detail_display = _localized(
                    "网页搜索 provider 已配置。",
                    "A web search provider is configured.",
                )
            elif browser_state.available:
                status = "limited"
                status_label = "Fetch + browser"
                status_detail = "Direct fetch and managed browser automation are available."
                status_detail_display = _localized(
                    "当前可直接抓取网页，也可使用托管浏览器自动化。",
                    "Direct fetch and managed browser automation are available.",
                )
            elif browser_enabled and browser_state.reason != "disabled":
                status = "limited"
                status_label = "Fetch only"
                status_detail = browser_state.detail
                status_detail_display = _localized(
                    "当前只有直接抓取可用；浏览器 runtime 尚未就绪。",
                    "Fetch is available, but the managed browser runtime is not ready yet.",
                )
            else:
                status = "limited"
                status_label = "Fetch only"
                status_detail = "Add a search provider key to enable fresh search."
                status_detail_display = _localized(
                    "当前只有抓取能力可用；若要启用联网搜索，请配置 provider key。",
                    "Fetch is available, but live search still needs a provider key.",
                )
            config_values = {
                "provider": provider,
                "braveApiKey": brave,
                "tavilyApiKey": tavily,
                "exaApiKey": exa,
                "maxResults": _non_bool_int(
                    _get_path(config_data, "tools.web.search.maxResults", 5), 5
                ),
                "browserEnabled": browser_enabled,
                "browserAvailable": browser_state.available,
                "browserRuntimeReady": browser_state.runtime_ready,
                "browserRuntimeSource": browser_state.runtime_source,
                "browserRuntimeRoot": browser_state.runtime_root,
                "browserProfilePath": browser_state.profile_path,
                "browserStatusReason": browser_state.reason,
                "browserStatusDetail": browser_state.detail,
                "agentBrowserPath": browser_state.agent_browser_path,
                "browserExecutablePath": browser_state.browser_executable_path,
            }
            meta_lines.append(f"Search provider: {provider or 'auto'}")
            meta_lines.append(
                f"Managed browser: {'ready' if browser_state.available else browser_state.reason}"
            )
        elif spec.form_kind == "embedding":
            model = _as_str(_get_path(config_data, "tools.embedding.model", ""))
            api_key = _as_str(_get_path(config_data, "tools.embedding.apiKey", ""))
            enabled = bool(model and api_key)
            status = "ready" if enabled else "needs_setup"
            status_label = "Configured" if enabled else "Needs setup"
            status_detail = model or "Add a model and API key to enable embeddings."
            status_detail_display = _localized(
                "Embedding 模型与密钥已配置。" if enabled else "配置模型和 API Key 后，语义检索才会启用。",
                "Embedding model and key are configured."
                if enabled
                else "Configure a model and API key to enable semantic retrieval.",
            )
            config_values = {
                "model": model,
                "apiKey": api_key,
                "baseUrl": _as_str(_get_path(config_data, "tools.embedding.baseUrl", "")),
                "dim": _non_bool_int(_get_path(config_data, "tools.embedding.dim", 0), 0),
            }
            meta_lines.append(f"Model: {model or 'none'}")
        elif spec.form_kind == "image_generation":
            model = _as_str(_get_path(config_data, "tools.imageGeneration.model", ""))
            api_key = _as_str(_get_path(config_data, "tools.imageGeneration.apiKey", ""))
            enabled = bool(api_key)
            status = "ready" if enabled else "needs_setup"
            status_label = "Configured" if enabled else "Needs setup"
            status_detail = model or "Configure an API key to enable image generation."
            status_detail_display = _localized(
                "图像生成模型已可用。" if enabled else "配置图像模型或 API Key 后才会启用。",
                "Image generation is configured."
                if enabled
                else "Configure a model or API key to enable image generation.",
            )
            config_values = {
                "apiKey": api_key,
                "model": model,
                "baseUrl": _as_str(_get_path(config_data, "tools.imageGeneration.baseUrl", "")),
            }
            meta_lines.append(f"Model: {model or 'default'}")
        elif spec.form_kind == "desktop":
            enabled = bool(_get_path(config_data, "tools.desktop.enabled", True))
            status = "ready" if enabled else "disabled"
            status_label = "Enabled" if enabled else "Disabled"
            status_detail = (
                "Desktop automation is available to the agent."
                if enabled
                else "Enable desktop automation before Bao can act on the local UI."
            )
            status_detail_display = _localized(
                "本地桌面控制已开启。" if enabled else "本地桌面控制当前关闭。",
                "Desktop control is enabled." if enabled else "Desktop control is currently disabled.",
            )
            config_values = {"enabled": enabled}
        elif spec.form_kind == "coding":
            backends = _coding_backends()
            status = "ready" if backends else "unavailable"
            status_label = "Available" if backends else "No backend"
            status_detail = (
                ", ".join(backends)
                if backends
                else "Install OpenCode, Codex, or Claude Code to activate coding delegation."
            )
            status_detail_display = _localized(
                "已检测到编程后端。" if backends else "尚未检测到 OpenCode、Codex 或 Claude Code。",
                "Coding backends detected."
                if backends
                else "No OpenCode, Codex, or Claude Code backend detected yet.",
            )
            config_values = {"backends": backends}
            meta_lines.append(status_detail)

        if spec.form_kind == "overview":
            if spec.id == "cron":
                status = "configured"
                status_label = "Runtime-managed"
                status_detail = "Available when the gateway starts with cron support."
                status_detail_display = _localized(
                    "Cron 只有在运行时挂上 cron service 时才会真正可用；这里先展示它的职责边界。",
                    "Available when the gateway starts with cron support.",
                )
            else:
                status = "ready"
                status_label = "Core"
                status_detail = spec.detail
                status_detail_display = _localized(spec.detail_zh, spec.detail)

        return {
            "id": f"builtin:{spec.id}",
            "kind": "builtin",
            "source": "builtin",
            "name": spec.name,
            "displayName": _localized(spec.name_zh, spec.name),
            "bundle": spec.bundle,
            "summary": spec.summary,
            "displaySummary": _localized(spec.summary_zh, spec.summary),
            "detail": spec.detail,
            "displayDetail": _localized(spec.detail_zh, spec.detail),
            "capabilities": list(spec.capabilities),
            "includedTools": list(spec.included_tools),
            "status": status,
            "statusLabel": status_label,
            "statusDetail": status_detail,
            "statusDetailDisplay": status_detail_display,
            "needsAttention": _attention_status(status),
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

    def _build_mcp_server_items(
        self,
        config_data: dict[str, object],
        probe_results: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        server_map = _as_dict(_get_path(config_data, "tools.mcpServers", {})) or {}
        items: list[dict[str, object]] = []
        for name, raw_value in server_map.items():
            server_cfg = _as_dict(raw_value) or {}
            probe = probe_results.get(name, {})
            probe_tool_names = [str(item) for item in (_as_list(probe.get("toolNames")) or [])]
            command = _as_str(server_cfg.get("command", ""))
            url = _as_str(server_cfg.get("url", ""))
            args = [str(item) for item in (_as_list(server_cfg.get("args")) or [])]
            env = {str(k): str(v) for k, v in (_as_dict(server_cfg.get("env")) or {}).items()}
            headers = {
                str(k): str(v) for k, v in (_as_dict(server_cfg.get("headers")) or {}).items()
            }
            transport = _mcp_transport(command, url)
            status, status_label, status_detail, status_detail_display = _mcp_status(
                transport=transport,
                probe=probe,
                tool_count=len(probe_tool_names),
            )
            items.append(
                {
                    "id": f"mcp:{name}",
                    "kind": "mcp_server",
                    "source": "mcp",
                    "name": name,
                    "displayName": _localized(name, name),
                    "bundle": "mcp",
                    "summary": "External MCP server definition.",
                    "displaySummary": _localized(
                        "外部 MCP 服务定义。",
                        "External MCP server definition.",
                    ),
                    "detail": "MCP servers expand into runtime tools after a successful handshake.",
                    "displayDetail": _localized(
                        "MCP 服务在握手成功后会展开为运行时工具。",
                        "MCP servers expand into runtime tools after a successful handshake.",
                    ),
                    "capabilities": [
                        transport.upper() if transport != "unconfigured" else "Setup",
                        "External",
                        "MCP",
                    ],
                    "includedTools": probe_tool_names,
                    "status": status,
                    "statusLabel": status_label,
                    "statusDetail": status_detail,
                    "statusDetailDisplay": status_detail_display,
                    "needsAttention": _attention_status(status),
                    "formKind": "mcp_server",
                    "configValues": {
                        "previousName": name,
                        "name": name,
                        "transport": transport,
                        "command": command,
                        "argsText": "\n".join(args),
                        "envText": "\n".join(f"{key}={value}" for key, value in env.items()),
                        "url": url,
                        "headersText": "\n".join(
                            f"{key}: {value}" for key, value in headers.items()
                        ),
                        "toolTimeoutSeconds": _non_bool_int(
                            server_cfg.get("toolTimeoutSeconds"), 30
                        ),
                        "maxTools": _non_bool_int(server_cfg.get("maxTools"), 0),
                        "slimSchema": server_cfg.get("slimSchema"),
                    },
                    "iconSource": "../resources/icons/sidebar-tools.svg",
                    "metaLines": [
                        f"Transport: {transport}",
                        f"Timeout: {_non_bool_int(server_cfg.get('toolTimeoutSeconds'), 30)}s",
                    ],
                    "probe": dict(probe),
                    "searchText": " ".join(
                        [name, transport, command, url, "mcp", *probe_tool_names]
                    ).lower(),
                }
            )
        return items

    @staticmethod
    def _sort_key(item: dict[str, object]) -> tuple[int, int, str]:
        source_rank = 0 if item.get("kind") == "builtin" else 1
        attention_rank = 0 if bool(item.get("needsAttention")) else 1
        return (source_rank, attention_rank, str(item.get("name") or "").lower())
