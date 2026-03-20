from __future__ import annotations

from dataclasses import dataclass


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


def iconoir(name: str) -> str:
    return f"../resources/icons/vendor/iconoir/{name}.svg"


def localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def as_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def as_list(value: object) -> list[object] | None:
    return value if isinstance(value, list) else None


def as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def non_bool_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def get_path(data: dict[str, object], dotpath: str, default: object = None) -> object:
    node: object = data
    for part in dotpath.split("."):
        current = as_dict(node)
        if current is None or part not in current:
            return default
        node = current[part]
    return node


def attention_status(status: str) -> bool:
    return status in {"limited", "disabled", "needs_setup", "error", "unavailable", "blocked"}


def desktop_missing_dependencies() -> list[str]:
    import importlib.util

    missing: list[str] = []
    for label, module_name in (("mss", "mss"), ("pyautogui", "pyautogui"), ("Pillow", "PIL")):
        if importlib.util.find_spec(module_name) is None:
            missing.append(label)
    return missing


def coding_backends() -> tuple[list[str], list[str]]:
    import importlib
    import shutil

    backends: list[str] = []
    errors: list[str] = []
    for label, binary, module_path, class_name in (
        ("OpenCode", "opencode", "bao.agent.tools.opencode", "OpenCodeTool"),
        ("Codex", "codex", "bao.agent.tools.codex", "CodexTool"),
        ("Claude Code", "claude", "bao.agent.tools.claudecode", "ClaudeCodeTool"),
    ):
        if not shutil.which(binary):
            continue
        try:
            module = importlib.import_module(module_path)
            getattr(module, class_name)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            continue
        backends.append(label)
    return backends, errors


def mcp_transport(command: str, url: str) -> str:
    if command:
        return "stdio"
    if url:
        return "http"
    return "unconfigured"


def mcp_status_display(*, status: str, probe_error: str, tool_count: int) -> dict[str, str]:
    if status == "healthy":
        return localized(f"握手成功，已发现 {tool_count} 个运行时工具", f"{tool_count} runtime tools discovered")
    if status == "needs_setup":
        return localized("补充 command 或 URL 后即可测试。", "Add a command or URL, then test the connection.")
    if status == "configured":
        return localized("定义已保存，建议立即做一次探测。", "The definition is saved; run a probe next.")
    if probe_error:
        return localized(probe_error, probe_error)
    return localized("最近一次探测失败。", "Probe failed")


def mcp_status(
    *,
    transport: str,
    probe: dict[str, object],
    tool_count: int,
) -> tuple[str, str, str, dict[str, str]]:
    probe_error = as_str(probe.get("error"))
    if transport == "unconfigured":
        status, label, detail = "needs_setup", "Needs setup", "Add either a stdio command or an HTTP URL."
    elif not probe:
        status, label, detail = "configured", "Configured", "Ready to test"
    elif bool(probe.get("canConnect")):
        status, label, detail = "healthy", "Connected", f"{tool_count} runtime tools discovered"
    else:
        status, label, detail = "error", "Connection failed", probe_error or "Probe failed"
    return status, label, detail, mcp_status_display(
        status=status,
        probe_error=probe_error,
        tool_count=tool_count,
    )


def build_overview(items: list[dict[str, object]], config_data: dict[str, object]) -> dict[str, object]:
    builtin_count = sum(1 for item in items if item.get("kind") == "builtin")
    server_count = sum(1 for item in items if item.get("kind") == "mcp_server")
    attention_count = sum(1 for item in items if bool(item.get("needsAttention")))
    runtime_count = sum(1 for item in items if item.get("status") == "healthy")
    tools_cfg = as_dict(get_path(config_data, "tools", {})) or {}
    exposure = as_dict(tools_cfg.get("toolExposure")) or {}
    domains = as_list(exposure.get("domains")) or []
    return {
        "builtinCount": builtin_count,
        "mcpServerCount": server_count,
        "attentionCount": attention_count,
        "runningNowCount": runtime_count,
        "toolExposureMode": as_str(exposure.get("mode"), "off") or "off",
        "toolExposureDomains": [str(item) for item in domains],
        "restrictToWorkspace": bool(tools_cfg.get("restrictToWorkspace")),
        "desktopEnabled": bool(get_path(config_data, "tools.desktop.enabled", True)),
    }


def sort_key(item: dict[str, object]) -> tuple[int, int, str]:
    source_rank = 0 if item.get("kind") == "builtin" else 1
    attention_rank = 0 if bool(item.get("needsAttention")) else 1
    return (source_rank, attention_rank, str(item.get("name") or "").lower())
