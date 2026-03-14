from __future__ import annotations

from dataclasses import dataclass

from bao.agent.skill_catalog import SkillCatalog
from bao.agent.tool_catalog import ToolCatalog


@dataclass(frozen=True)
class SkillWorkspaceSnapshot:
    items: tuple[dict[str, object], ...]
    overview: dict[str, object]
    selected_id: str
    selected_item: dict[str, object]


_SECTION_ORDER = {
    "ready": 0,
    "needs_setup": 1,
    "instruction_only": 2,
    "shadowed": 3,
}

_SECTION_TITLES = {
    "ready": {"zh": "现在可用", "en": "Ready now"},
    "needs_setup": {"zh": "需设置", "en": "Needs setup"},
    "instruction_only": {"zh": "仅指导", "en": "Instruction only"},
    "shadowed": {"zh": "已覆盖", "en": "Overridden"},
}

_STATUS_DISPLAY = {
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

_ICON_MAP = {
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


def _localized(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _skill_icon_source(icon_name: str) -> str:
    return _ICON_MAP.get(icon_name, _ICON_MAP["book"])


def _attention_status(status: str) -> bool:
    return status in {"limited", "disabled", "needs_setup", "error", "unavailable"}


def _family_key(item_id: object) -> str:
    item_text = str(item_id or "")
    if ":" not in item_text:
        return item_text
    return item_text.split(":", 1)[1]


def _build_tool_maps(config_data: dict[str, object]) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    builtin_items = [
        item
        for item in ToolCatalog().list_items(config_data)
        if item.get("kind") == "builtin"
    ]
    family_map = {_family_key(item.get("id")): item for item in builtin_items}
    tool_map: dict[str, dict[str, object]] = {}
    for item in builtin_items:
        for tool_name in _as_list(item.get("includedTools")):
            if isinstance(tool_name, str) and tool_name:
                tool_map[tool_name] = item
    return family_map, tool_map


def _linked_capabilities(
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    refs = [str(item) for item in _as_list(record.get("capabilityRefs")) if str(item)]
    linked: list[dict[str, object]] = []
    for ref in refs:
        item = family_map.get(ref)
        if item is None:
            continue
        linked.append(
            {
                "id": ref,
                "displayName": dict(_as_dict(item.get("displayName"))),
                "status": str(item.get("status") or ""),
                "statusLabel": str(item.get("statusLabel") or ""),
                "statusDetailDisplay": dict(_as_dict(item.get("statusDetailDisplay"))),
                "iconSource": str(item.get("iconSource") or ""),
            }
        )
    return linked


def _resolve_activation_items(
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
    tool_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    refs = [str(item) for item in _as_list(record.get("activationRefs")) if str(item)]
    if not refs:
        refs = [str(item) for item in _as_list(record.get("capabilityRefs")) if str(item)]
    resolved: list[dict[str, object]] = []
    seen: set[str] = set()
    for ref in refs:
        item = family_map.get(ref) or tool_map.get(ref)
        if item is None:
            continue
        item_id = str(item.get("id") or ref)
        if item_id in seen:
            continue
        seen.add(item_id)
        resolved.append(item)
    return resolved


def _item_ready(item: dict[str, object]) -> bool:
    return not _attention_status(str(item.get("status") or ""))


def _status_payload(
    record: dict[str, object],
    activation_items: list[dict[str, object]],
) -> tuple[str, dict[str, str]]:
    missing_requirements = _as_str(record.get("missingRequirements"))
    if missing_requirements:
        return "needs_setup", _localized(
            f"缺失依赖：{missing_requirements}",
            f"Missing requirements: {missing_requirements}",
        )

    if activation_items:
        if all(_item_ready(item) for item in activation_items):
            names = [
                _as_str(_as_dict(item.get("displayName")).get("zh"))
                or _as_str(item.get("name"))
                for item in activation_items
            ]
            joined = "、".join(name for name in names if name)
            return "ready", _localized(
                f"当前可直接配合 {joined} 使用。" if joined else _STATUS_DISPLAY["ready"]["detail"]["zh"],
                f"Ready with {', '.join(name for name in names if name)}."
                if names
                else _STATUS_DISPLAY["ready"]["detail"]["en"],
            )

        detail = next(
            (
                _as_dict(item.get("statusDetailDisplay"))
                for item in activation_items
                if _attention_status(str(item.get("status") or ""))
            ),
            {},
        )
        return "needs_setup", {
            "zh": _as_str(detail.get("zh")) or _STATUS_DISPLAY["needs_setup"]["detail"]["zh"],
            "en": _as_str(detail.get("en")) or _STATUS_DISPLAY["needs_setup"]["detail"]["en"],
        }

    return "instruction_only", dict(_STATUS_DISPLAY["instruction_only"]["detail"])


def _matches_filters(item: dict[str, object], *, source_filter: str, query: str) -> bool:
    if source_filter == "workspace" and item.get("source") != "workspace":
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
    return query in _as_str(item.get("searchText")).lower()


def _sort_key(item: dict[str, object]) -> tuple[int, int, str, str]:
    section_rank = _SECTION_ORDER.get(_as_str(item.get("sectionKey")), 99)
    source_rank = 0 if item.get("source") == "workspace" else 1
    return (section_rank, source_rank, _as_str(item.get("displayNameText")).lower(), _as_str(item.get("name")).lower())


def _display_payload(record: dict[str, object]) -> dict[str, object]:
    display_name = _as_str(record.get("displayName")) or _as_str(record.get("name"))
    display_name_zh = _as_str(record.get("displayNameZh")) or display_name
    summary = _as_str(record.get("description")) or display_name
    detail_zh = _as_str(record.get("displayDescriptionZh")) or summary
    return {
        "name": display_name,
        "nameZh": display_name_zh,
        "summary": summary,
        "detail": summary,
        "detailZh": detail_zh,
    }


def _build_search_text(
    *,
    record: dict[str, object],
    display: dict[str, object],
    status: str,
    status_detail_display: dict[str, str],
    linked_capabilities: list[dict[str, object]],
    example_prompts: list[str],
) -> str:
    return " ".join(
        [
            _as_str(record.get("name")),
            _as_str(display.get("name")),
            _as_str(display.get("nameZh")),
            _as_str(display.get("summary")),
            _as_str(display.get("detailZh")),
            _STATUS_DISPLAY[status]["label"]["en"],
            _STATUS_DISPLAY[status]["label"]["zh"],
            status_detail_display["en"],
            status_detail_display["zh"],
            *example_prompts,
            *[_as_str(item.get("id")) for item in linked_capabilities],
        ]
    ).lower()


def _build_skill_item(
    *,
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
    tool_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    activation_items = _resolve_activation_items(record, family_map, tool_map)
    linked_capabilities = _linked_capabilities(record, family_map)
    status, status_detail_display = _status_payload(record, activation_items)
    section_key = "shadowed" if bool(record.get("shadowed")) else status
    display = _display_payload(record)
    example_prompts = [str(item) for item in _as_list(record.get("examplePrompts")) if str(item)]
    return {
        "id": _as_str(record.get("id")),
        "name": _as_str(record.get("name")),
        "source": _as_str(record.get("source")),
        "displayName": _localized(_as_str(display.get("nameZh")), _as_str(display.get("name"))),
        "displayNameText": _as_str(display.get("name")),
        "displaySummary": _localized(_as_str(display.get("detailZh")), _as_str(display.get("summary"))),
        "displayDetail": _localized(_as_str(display.get("detailZh")), _as_str(display.get("detail"))),
        "description": _as_str(display.get("summary")),
        "summary": _as_str(display.get("summary")),
        "detail": _as_str(display.get("detail")),
        "status": status,
        "statusLabel": _localized(
            _STATUS_DISPLAY[status]["label"]["zh"],
            _STATUS_DISPLAY[status]["label"]["en"],
        ),
        "statusDetailDisplay": status_detail_display,
        "needsAttention": status != "ready",
        "shadowed": bool(record.get("shadowed")),
        "always": bool(record.get("always")),
        "missingRequirements": _as_str(record.get("missingRequirements")),
        "path": _as_str(record.get("path")),
        "canEdit": bool(record.get("canEdit")),
        "canDelete": bool(record.get("canDelete")),
        "iconSource": _skill_icon_source(_as_str(record.get("icon"), "book")),
        "category": _as_str(record.get("category"), "general"),
        "sectionKey": section_key,
        "sectionTitle": dict(_SECTION_TITLES[section_key]),
        "linkedCapabilities": linked_capabilities,
        "linkedCapabilityRefs": [item["id"] for item in linked_capabilities],
        "examplePrompts": example_prompts,
        "metadata": dict(_as_dict(record.get("metadata"))),
        "searchText": _build_search_text(
            record=record,
            display=display,
            status=status,
            status_detail_display=status_detail_display,
            linked_capabilities=linked_capabilities,
            example_prompts=example_prompts,
        ),
    }


def _build_overview(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "totalCount": len(items),
        "workspaceCount": sum(1 for item in items if item.get("source") == "workspace"),
        "readyCount": sum(1 for item in items if item.get("status") == "ready"),
        "needsSetupCount": sum(1 for item in items if item.get("status") == "needs_setup"),
        "instructionOnlyCount": sum(1 for item in items if item.get("status") == "instruction_only"),
        "shadowedCount": sum(1 for item in items if bool(item.get("shadowed"))),
    }


def _mark_section_headers(items: list[dict[str, object]]) -> None:
    previous_section = ""
    for item in items:
        section_key = _as_str(item.get("sectionKey"))
        item["showSectionHeader"] = section_key != previous_section
        previous_section = section_key


def build_skill_workspace_snapshot(
    *,
    catalog: SkillCatalog,
    config_data: dict[str, object],
    query: str,
    source_filter: str,
    selected_id: str,
) -> SkillWorkspaceSnapshot:
    family_map, tool_map = _build_tool_maps(config_data)
    records = catalog.list_records()
    items = [
        _build_skill_item(record=record, family_map=family_map, tool_map=tool_map)
        for record in records
    ]
    overview = _build_overview(items)
    filtered = [item for item in items if _matches_filters(item, source_filter=source_filter, query=query)]
    filtered.sort(key=_sort_key)
    _mark_section_headers(filtered)

    selected_item = next(
        (item for item in filtered if item.get("id") == selected_id),
        filtered[0] if filtered else {},
    )
    next_selected_id = _as_str(selected_item.get("id")) if selected_item else ""
    next_selected_item = dict(selected_item) if selected_item else {}
    return SkillWorkspaceSnapshot(
        items=tuple(dict(item) for item in filtered),
        overview=overview,
        selected_id=next_selected_id,
        selected_item=next_selected_item,
    )
