from __future__ import annotations

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
    "domain_disabled": ("未参与自动暴露", "Domain disabled"),
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


def as_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def as_list(value: object) -> list[object] | None:
    return value if isinstance(value, list) else None


def as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def get_path(data: dict[str, object], dotpath: str, default: object = None) -> object:
    node: object = data
    for part in dotpath.split("."):
        current = as_dict(node)
        if current is None or part not in current:
            return default
        node = current[part]
    return node


def normalize_list(value: object) -> list[str]:
    return [str(item) for item in (as_list(value) or []) if str(item).strip()]


def config_values(item: dict[str, object]) -> dict[str, object]:
    return as_dict(item.get("configValues")) or {}


def localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def empty_localized() -> dict[str, str]:
    return localized("", "")


def localized_label(labels: dict[str, tuple[str, str]], key: str) -> dict[str, str]:
    zh, en = labels.get(key, (key, key))
    return localized(zh, en)


def flatten_localized(value: object) -> str:
    data = as_dict(value)
    if data is None:
        return as_str(value)
    return as_str(data.get("zh")) or as_str(data.get("en"))
def matches_filters(item: dict[str, object], *, source_filter: str, query: str) -> bool:
    if source_filter == "builtin" and item.get("kind") != "builtin":
        return False
    if source_filter == "mcp" and item.get("kind") != "mcp_server":
        return False
    if source_filter == "attention" and not bool(item.get("needsAttention")):
        return False
    if not query:
        return True
    return query in str(item.get("searchText") or "").lower()
