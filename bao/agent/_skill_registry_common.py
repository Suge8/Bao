from __future__ import annotations

from bao.agent.skill_catalog import USER_SKILL_SOURCE
from bao.agent.tool_catalog import ToolCatalog

SECTION_ORDER = {
    "ready": 0,
    "needs_setup": 1,
    "instruction_only": 2,
    "shadowed": 3,
}

SECTION_TITLES = {
    "ready": {"zh": "现在可用", "en": "Ready now"},
    "needs_setup": {"zh": "需设置", "en": "Needs setup"},
    "instruction_only": {"zh": "仅指导", "en": "Instruction only"},
    "shadowed": {"zh": "已覆盖", "en": "Overridden"},
}

STATUS_DISPLAY = {
    "ready": {
        "label": {"zh": "可直接使用", "en": "Ready"},
        "detail": {"zh": "当前技能所需能力已就绪。", "en": "This skill can run with the current setup."},
    },
    "needs_setup": {
        "label": {"zh": "需设置", "en": "Needs setup"},
        "detail": {
            "zh": "先补齐依赖或启用相关能力，再使用这个技能。",
            "en": "Finish setup or enable the linked capability before using this skill.",
        },
    },
    "instruction_only": {
        "label": {"zh": "仅指导", "en": "Instruction only"},
        "detail": {
            "zh": "这是流程或写作指导，不依赖当前暴露的 Bao 工具。",
            "en": "This skill is guidance-only and does not rely on a current Bao tool surface.",
        },
    },
}

ICON_MAP = {
    "browser": "../resources/icons/vendor/iconoir/page-search.svg",
    "toolbox": "../resources/icons/vendor/lucide-lab/toolbox.svg",
    "computer": "../resources/icons/vendor/iconoir/computer.svg",
    "message": "../resources/icons/vendor/iconoir/message-text.svg",
    "calendar": "../resources/icons/vendor/iconoir/calendar-rotate.svg",
    "brain": "../resources/icons/vendor/iconoir/brain-electricity.svg",
    "spark": "../resources/icons/vendor/iconoir/circle-spark.svg",
    "book": "../resources/icons/vendor/iconoir/book-stack.svg",
    "activity": "../resources/icons/vendor/iconoir/activity.svg",
    "database": "../resources/icons/vendor/iconoir/database-settings.svg",
    "weather": "../resources/icons/vendor/iconoir/activity.svg",
}


def localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def skill_icon_source(icon_name: str) -> str:
    return ICON_MAP.get(icon_name, ICON_MAP["book"])


def attention_status(status: str) -> bool:
    return status in {"limited", "disabled", "needs_setup", "error", "unavailable"}


def family_key(item_id: object) -> str:
    item_text = str(item_id or "")
    if ":" not in item_text:
        return item_text
    return item_text.split(":", 1)[1]


def build_tool_maps(
    config_data: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    builtin_items = [
        item
        for item in ToolCatalog().list_items(config_data)
        if item.get("kind") == "builtin"
    ]
    family_map = {family_key(item.get("id")): item for item in builtin_items}
    tool_map: dict[str, dict[str, object]] = {}
    for item in builtin_items:
        for tool_name in as_list(item.get("includedTools")):
            if isinstance(tool_name, str) and tool_name:
                tool_map[tool_name] = item
    return family_map, tool_map


def matches_filters(item: dict[str, object], *, source_filter: str, query: str) -> bool:
    if source_filter == USER_SKILL_SOURCE and item.get("source") != USER_SKILL_SOURCE:
        return False
    if source_filter == "ready" and item.get("status") != "ready":
        return False
    if source_filter == "needs_setup" and item.get("status") != "needs_setup":
        return False
    if source_filter == "instruction_only" and item.get("status") != "instruction_only":
        return False
    if source_filter == "shadowed" and not bool(item.get("shadowed")):
        return False
    if not query:
        return True
    return query in as_str(item.get("searchText")).lower()


def sort_key(item: dict[str, object]) -> tuple[int, int, str, str]:
    section_rank = SECTION_ORDER.get(as_str(item.get("sectionKey")), 99)
    source_rank = 0 if item.get("source") == USER_SKILL_SOURCE else 1
    return (
        section_rank,
        source_rank,
        as_str(item.get("displayNameText")).lower(),
        as_str(item.get("name")).lower(),
    )


def build_overview(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "totalCount": len(items),
        "userCount": sum(1 for item in items if item.get("source") == USER_SKILL_SOURCE),
        "readyCount": sum(1 for item in items if item.get("status") == "ready"),
        "needsSetupCount": sum(1 for item in items if item.get("status") == "needs_setup"),
        "instructionOnlyCount": sum(1 for item in items if item.get("status") == "instruction_only"),
        "shadowedCount": sum(1 for item in items if bool(item.get("shadowed"))),
    }


def mark_section_headers(items: list[dict[str, object]]) -> None:
    previous_section = ""
    for item in items:
        section_key = as_str(item.get("sectionKey"))
        item["showSectionHeader"] = section_key != previous_section
        previous_section = section_key
