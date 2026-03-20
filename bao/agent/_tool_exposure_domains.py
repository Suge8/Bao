from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

TOOL_DOMAIN_CORE = "core"
TOOL_DOMAIN_MESSAGING = "messaging"
TOOL_DOMAIN_HANDOFF = "handoff"
TOOL_DOMAIN_WEB = "web_research"
TOOL_DOMAIN_DESKTOP = "desktop_automation"
TOOL_DOMAIN_CODING = "coding_backend"

DEFAULT_TOOL_EXPOSURE_DOMAINS = (
    TOOL_DOMAIN_CORE,
    TOOL_DOMAIN_MESSAGING,
    TOOL_DOMAIN_HANDOFF,
    TOOL_DOMAIN_WEB,
    TOOL_DOMAIN_DESKTOP,
    TOOL_DOMAIN_CODING,
)
TOOL_EXPOSURE_DOMAINS = frozenset(DEFAULT_TOOL_EXPOSURE_DOMAINS)

TOOL_EXPOSURE_DOMAIN_LABELS = {
    TOOL_DOMAIN_CORE: ("核心本地", "Core local"),
    TOOL_DOMAIN_MESSAGING: ("消息发送", "Messaging"),
    TOOL_DOMAIN_HANDOFF: ("会话接力", "Handoff"),
    TOOL_DOMAIN_WEB: ("网页检索", "Web research"),
    TOOL_DOMAIN_DESKTOP: ("桌面自动化", "Desktop automation"),
    TOOL_DOMAIN_CODING: ("代码任务", "Coding backend"),
}
TOOL_EXPOSURE_DOMAIN_DESCRIPTIONS = {
    TOOL_DOMAIN_CORE: ("文件、命令与基础本地能力。", "Files, shell, and core local capabilities."),
    TOOL_DOMAIN_MESSAGING: ("会话查找与目标解析。", "Session discovery and target resolution."),
    TOOL_DOMAIN_HANDOFF: ("把内容转交到别的会话，并由 runtime 负责回执与结果回流。", "Hand work to another session with runtime-managed receipts and result routing."),
    TOOL_DOMAIN_WEB: ("网页搜索、抓取与浏览器研究。", "Web search, fetch, and browser-driven research."),
    TOOL_DOMAIN_DESKTOP: ("截屏、点击、输入等桌面自动化。", "Screenshot, click, type, and other desktop automation actions."),
    TOOL_DOMAIN_CODING: ("读写文件、执行命令与 coding backend。", "File editing, shell execution, and coding backends."),
}
TOOL_EXPOSURE_DOMAIN_SEARCH_HINTS = {
    TOOL_DOMAIN_CORE: (
        "local files shell workspace command memory plan read write edit list dir exec",
        "本地 文件 命令 工作区 记忆 计划 读取 写入 编辑 目录 执行",
    ),
    TOOL_DOMAIN_MESSAGING: (
        "send message recipient target session discovery lookup resolve default recent telegram tg imessage slack discord whatsapp",
        "发消息 发个消息 发给 收件目标 目标会话 会话查找 解析 默认 最近 telegram tg imessage slack discord whatsapp",
    ),
    TOOL_DOMAIN_HANDOFF: (
        "handoff send to session transfer cross session cross profile route hand off",
        "转交 接力 转到 交给 跨会话 跨 profile 那边处理 那边去发",
    ),
    TOOL_DOMAIN_WEB: (
        "web url http https website webpage search fetch crawl docs latest news browse browser",
        "网页 网站 链接 搜索 抓取 文档 资料 新闻 最新 新特性 最佳实践 官网 浏览器",
    ),
    TOOL_DOMAIN_DESKTOP: (
        "desktop screen screenshot click type input drag scroll ui pointer keyboard",
        "桌面 屏幕 截图 点击 输入 拖拽 滚动 界面 指针 键盘",
    ),
    TOOL_DOMAIN_CODING: (
        "code coding repo git patch test debug refactor python qml typescript javascript file py ts tsx jsx json yaml toml md",
        "代码 仓库 修改 修复 测试 调试 重构 脚本 文件 python qml typescript",
    ),
}

_MESSAGING_TOOLS = frozenset({"session_default", "session_lookup", "session_recent", "session_resolve"})
_HANDOFF_TOOLS = frozenset(
    {"send_to_session", "session_default", "session_lookup", "session_recent", "session_resolve"}
)
_WEB_TOOLS = frozenset({"web_search", "web_fetch", "agent_browser"})
_DESKTOP_TOOLS = frozenset(
    {"screenshot", "click", "type_text", "key_press", "scroll", "drag", "get_screen_info"}
)
_CORE_FILESYSTEM_TOOLS = frozenset({"read_file", "write_file", "edit_file", "list_dir", "exec"})
_CORE_MEMORY_TOOLS = frozenset({"remember", "forget", "update_memory"})
_CORE_ORCHESTRATION_TOOLS = frozenset({"create_plan", "update_plan_step", "clear_plan", "spawn"})
_CODING_AGENT_TOOLS = frozenset({"coding_agent", "coding_agent_details"})
_CODING_PREFIXES = ("codex", "opencode", "claudecode")

REQUIRED_TOOLS_BY_DOMAIN = {
    TOOL_DOMAIN_CORE: _CORE_FILESYSTEM_TOOLS | _CORE_MEMORY_TOOLS | _CORE_ORCHESTRATION_TOOLS,
    TOOL_DOMAIN_MESSAGING: _MESSAGING_TOOLS,
    TOOL_DOMAIN_HANDOFF: _HANDOFF_TOOLS,
    TOOL_DOMAIN_WEB: frozenset({"web_fetch", "web_search", "agent_browser"}),
    TOOL_DOMAIN_DESKTOP: _DESKTOP_TOOLS,
    TOOL_DOMAIN_CODING: _CORE_FILESYSTEM_TOOLS | frozenset({"coding_agent"}),
}
ORDERED_REQUIRED_TOOLS_BY_DOMAIN = {
    TOOL_DOMAIN_CORE: (
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "exec",
        "remember",
        "forget",
        "update_memory",
        "create_plan",
        "update_plan_step",
        "clear_plan",
        "spawn",
    ),
    TOOL_DOMAIN_MESSAGING: (
        "session_default",
        "session_lookup",
        "session_recent",
        "session_resolve",
    ),
    TOOL_DOMAIN_HANDOFF: (
        "send_to_session",
        "session_default",
        "session_lookup",
        "session_recent",
        "session_resolve",
    ),
    TOOL_DOMAIN_WEB: ("web_search", "web_fetch", "agent_browser"),
    TOOL_DOMAIN_DESKTOP: (
        "screenshot",
        "click",
        "type_text",
        "key_press",
        "scroll",
        "drag",
        "get_screen_info",
    ),
    TOOL_DOMAIN_CODING: (
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "exec",
        "coding_agent",
    ),
}


@dataclass(frozen=True, slots=True)
class ToolExposureDomainDoc:
    key: str
    title_zh: str
    title_en: str
    description_zh: str
    description_en: str
    tool_names: tuple[str, ...]
    search_hint_zh: str
    search_hint_en: str

    def content(self) -> str:
        parts = [
            self.key,
            self.search_hint_zh,
            self.search_hint_en,
        ]
        return "\n".join(part for part in parts if part)


def normalize_tool_exposure_domains(values: object) -> list[str]:
    if not isinstance(values, list):
        return list(DEFAULT_TOOL_EXPOSURE_DOMAINS)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        domain = str(value).strip().lower()
        if not domain or domain not in TOOL_EXPOSURE_DOMAINS or domain in seen:
            continue
        seen.add(domain)
        normalized.append(domain)
    if not normalized:
        return list(DEFAULT_TOOL_EXPOSURE_DOMAINS)
    if TOOL_DOMAIN_CORE not in seen:
        normalized.insert(0, TOOL_DOMAIN_CORE)
    return normalized


def domain_required_tools(domain: str) -> tuple[str, ...]:
    return tuple(sorted(REQUIRED_TOOLS_BY_DOMAIN.get(domain, ())))


def ordered_required_tools(domains: Iterable[str], available_names: set[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for domain in DEFAULT_TOOL_EXPOSURE_DOMAINS:
        if domain not in domains:
            continue
        for name in ORDERED_REQUIRED_TOOLS_BY_DOMAIN.get(domain, ()):
            if name in available_names and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def domain_doc(domain: str) -> ToolExposureDomainDoc:
    title_zh, title_en = TOOL_EXPOSURE_DOMAIN_LABELS[domain]
    description_zh, description_en = TOOL_EXPOSURE_DOMAIN_DESCRIPTIONS[domain]
    hint_en, hint_zh = TOOL_EXPOSURE_DOMAIN_SEARCH_HINTS[domain]
    return ToolExposureDomainDoc(
        key=domain,
        title_zh=title_zh,
        title_en=title_en,
        description_zh=description_zh,
        description_en=description_en,
        tool_names=ORDERED_REQUIRED_TOOLS_BY_DOMAIN[domain],
        search_hint_zh=hint_zh,
        search_hint_en=hint_en,
    )


def build_domain_search_rows(enabled_domains: Iterable[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for domain in DEFAULT_TOOL_EXPOSURE_DOMAINS:
        if domain not in enabled_domains or domain == TOOL_DOMAIN_CORE:
            continue
        doc = domain_doc(domain)
        rows.append({"key": domain, "content": doc.content()})
    return rows


def tool_domains_for_name(name: str) -> frozenset[str]:
    normalized = str(name).strip().lower()
    if not normalized:
        return frozenset({TOOL_DOMAIN_CORE})
    domains: set[str] = set()
    if normalized in _MESSAGING_TOOLS:
        domains.add(TOOL_DOMAIN_MESSAGING)
    if normalized in _HANDOFF_TOOLS:
        domains.add(TOOL_DOMAIN_HANDOFF)
    if normalized in _WEB_TOOLS:
        domains.add(TOOL_DOMAIN_WEB)
    if normalized in _DESKTOP_TOOLS:
        domains.add(TOOL_DOMAIN_DESKTOP)
    if normalized in _CORE_FILESYSTEM_TOOLS:
        domains.add(TOOL_DOMAIN_CORE)
    if normalized in _CODING_AGENT_TOOLS or normalized.startswith(_CODING_PREFIXES):
        domains.add(TOOL_DOMAIN_CODING)
    if not domains:
        domains.add(TOOL_DOMAIN_CORE)
    return frozenset(domains)


def item_domains_for_tools(tool_names: Iterable[str]) -> set[str]:
    domains: set[str] = set()
    for name in tool_names:
        domains.update(tool_domains_for_name(name))
    return domains
