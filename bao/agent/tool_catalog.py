from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinToolFamily:
    id: str
    name: str
    bundle: str
    summary: str
    detail: str
    capabilities: tuple[str, ...]
    included_tools: tuple[str, ...]
    form_kind: str = "overview"
    config_paths: tuple[str, ...] = ()


_BUILTIN_TOOL_FAMILIES: tuple[BuiltinToolFamily, ...] = (
    BuiltinToolFamily(
        id="filesystem",
        name="Local Files",
        bundle="core",
        summary="Read, write, edit, and list workspace files.",
        detail="These tools are the core local file surface for inspecting and changing project files.",
        capabilities=("Filesystem", "Workspace", "Authoring"),
        included_tools=("read_file", "write_file", "edit_file", "list_dir"),
    ),
    BuiltinToolFamily(
        id="exec",
        name="Terminal Exec",
        bundle="core",
        summary="Run shell commands on the runtime host with sandbox controls.",
        detail="Exec is the bridge to local shell workflows. Its scope is shaped by timeout, sandbox mode, and workspace restrictions.",
        capabilities=("Shell", "Local host", "Diagnostics"),
        included_tools=("exec",),
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
        bundle="code",
        summary="Delegate multi-file coding and debugging to external coding backends.",
        detail="Coding Agent routes heavier implementation work to installed coding backends such as OpenCode, Codex, or Claude Code.",
        capabilities=("Codegen", "Refactor", "Debug"),
        included_tools=("coding_agent", "coding_agent_details"),
        form_kind="coding",
    ),
    BuiltinToolFamily(
        id="web",
        name="Web Retrieval",
        bundle="web",
        summary="Search the web, fetch URLs, and automate browser flows.",
        detail="This family combines web search, direct fetch, and browser automation. Search quality depends on configured providers.",
        capabilities=("Search", "Fetch", "Browser"),
        included_tools=("web_search", "web_fetch", "agent_browser"),
        form_kind="web",
        config_paths=(
            "tools.web.search.provider",
            "tools.web.search.tavilyApiKey",
            "tools.web.search.braveApiKey",
            "tools.web.search.exaApiKey",
            "tools.web.search.maxResults",
        ),
    ),
    BuiltinToolFamily(
        id="embedding",
        name="Embeddings",
        bundle="core",
        summary="Provide semantic embeddings for memory and retrieval workflows.",
        detail="Embedding settings back semantic search and long-term memory quality. They stay dormant until a model and API key are configured.",
        capabilities=("Embeddings", "Retrieval", "Memory"),
        included_tools=("embedding_runtime",),
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
        bundle="core",
        summary="Create images from prompts when an image model is configured.",
        detail="Image generation is optional and only becomes active once a provider key is configured.",
        capabilities=("Image", "Creative", "Generation"),
        included_tools=("image_generation",),
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
        bundle="core",
        summary="Write, update, and remove explicit long-term memory entries.",
        detail="These tools let Bao persist explicit facts into the long-term memory system without opening the memory workspace manually.",
        capabilities=("Memory", "Persistence", "Curation"),
        included_tools=("remember", "forget", "update_memory"),
    ),
    BuiltinToolFamily(
        id="planning_subagents",
        name="Planning and Subagents",
        bundle="core",
        summary="Create plans and delegate longer tasks to subagents.",
        detail="This family covers linear planning, background subagent work, progress inspection, and task cancellation.",
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
    ),
    BuiltinToolFamily(
        id="message_diagnostics",
        name="Messaging and Diagnostics",
        bundle="core",
        summary="Send cross-channel messages and inspect runtime diagnostics.",
        detail="These tools cover explicit outbound delivery and structured internal diagnostics for framework-side failures.",
        capabilities=("Messaging", "Diagnostics", "Support"),
        included_tools=("message", "runtime_diagnostics"),
    ),
    BuiltinToolFamily(
        id="cron",
        name="Scheduled Tasks",
        bundle="core",
        summary="Schedule reminders and recurring workflows.",
        detail="Cron is active when the runtime includes the cron service and lets Bao manage scheduled reminders and routines.",
        capabilities=("Schedule", "Reminder", "Automation"),
        included_tools=("cron",),
    ),
    BuiltinToolFamily(
        id="desktop",
        name="Desktop Automation",
        bundle="desktop",
        summary="See and control the local desktop with screenshots and input actions.",
        detail="Desktop automation is powerful and high-risk. It should stay explicit, visible, and easy to disable.",
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
        form_kind="desktop",
        config_paths=("tools.desktop.enabled",),
    ),
)


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
        config_values: dict[str, object] = {}
        meta_lines: list[str] = []

        if spec.form_kind == "exec":
            sandbox_mode = _as_str(_get_path(config_data, "tools.exec.sandboxMode", "semi-auto"))
            restrict_to_workspace = bool(_get_path(config_data, "tools.restrictToWorkspace", False))
            status = "configured"
            status_label = "Workspace only" if restrict_to_workspace else "Configured"
            status_detail = f"Sandbox {sandbox_mode}"
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
            if enabled_search:
                status = "ready"
                status_label = "Search ready"
                status_detail = provider or "Provider auto-select"
            else:
                status = "limited"
                status_label = "Fetch only"
                status_detail = "Add a search provider key to enable fresh search."
            config_values = {
                "provider": provider,
                "braveApiKey": brave,
                "tavilyApiKey": tavily,
                "exaApiKey": exa,
                "maxResults": _non_bool_int(
                    _get_path(config_data, "tools.web.search.maxResults", 5), 5
                ),
            }
            meta_lines.append(f"Search provider: {provider or 'auto'}")
        elif spec.form_kind == "embedding":
            model = _as_str(_get_path(config_data, "tools.embedding.model", ""))
            api_key = _as_str(_get_path(config_data, "tools.embedding.apiKey", ""))
            enabled = bool(model and api_key)
            status = "ready" if enabled else "needs_setup"
            status_label = "Configured" if enabled else "Needs setup"
            status_detail = model or "Add a model and API key to enable embeddings."
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
            config_values = {"backends": backends}
            meta_lines.append(status_detail)

        if spec.form_kind == "overview":
            if spec.id == "cron":
                status = "configured"
                status_label = "Runtime-managed"
                status_detail = "Available when the gateway starts with cron support."
            else:
                status = "ready"
                status_label = "Core"
                status_detail = spec.detail

        return {
            "id": f"builtin:{spec.id}",
            "kind": "builtin",
            "source": "builtin",
            "name": spec.name,
            "bundle": spec.bundle,
            "summary": spec.summary,
            "detail": spec.detail,
            "capabilities": list(spec.capabilities),
            "includedTools": list(spec.included_tools),
            "status": status,
            "statusLabel": status_label,
            "statusDetail": status_detail,
            "needsAttention": _attention_status(status),
            "formKind": spec.form_kind,
            "configPaths": list(spec.config_paths),
            "configValues": config_values,
            "metaLines": meta_lines,
            "searchText": " ".join(
                [
                    spec.name,
                    spec.summary,
                    spec.detail,
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
            transport = "stdio" if command else ("http" if url else "unconfigured")
            status = "configured"
            status_label = "Configured"
            status_detail = "Ready to test"
            if transport == "unconfigured":
                status = "needs_setup"
                status_label = "Needs setup"
                status_detail = "Add either a stdio command or an HTTP URL."
            elif probe:
                if bool(probe.get("canConnect")):
                    status = "healthy"
                    status_label = "Connected"
                    count = len(_as_list(probe.get("toolNames")) or [])
                    status_detail = f"{count} runtime tools discovered"
                else:
                    status = "error"
                    status_label = "Connection failed"
                    status_detail = _as_str(probe.get("error"), "Probe failed")
            items.append(
                {
                    "id": f"mcp:{name}",
                    "kind": "mcp_server",
                    "source": "mcp",
                    "name": name,
                    "bundle": "mcp",
                    "summary": "External MCP server definition.",
                    "detail": "MCP servers expand into runtime tools after a successful handshake.",
                    "capabilities": [
                        transport.upper() if transport != "unconfigured" else "Setup",
                        "External",
                        "MCP",
                    ],
                    "includedTools": probe_tool_names,
                    "status": status,
                    "statusLabel": status_label,
                    "statusDetail": status_detail,
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
