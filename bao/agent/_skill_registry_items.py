from __future__ import annotations

from dataclasses import dataclass

from bao.agent._skill_registry_common import (
    SECTION_TITLES,
    STATUS_DISPLAY,
    as_dict,
    as_list,
    as_str,
    attention_status,
    localized,
    skill_icon_source,
)


@dataclass(frozen=True, slots=True)
class SearchTextRequest:
    record: dict[str, object]
    display: dict[str, object]
    status: str
    status_detail_display: dict[str, str]
    linked_capabilities: list[dict[str, object]]
    example_prompts: list[str]


def linked_capabilities(
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    refs = [str(item) for item in as_list(record.get("capabilityRefs")) if str(item)]
    linked: list[dict[str, object]] = []
    for ref in refs:
        item = family_map.get(ref)
        if item is None:
            continue
        linked.append(
            {
                "id": ref,
                "displayName": dict(as_dict(item.get("displayName"))),
                "status": str(item.get("status") or ""),
                "statusLabel": str(item.get("statusLabel") or ""),
                "statusDetailDisplay": dict(as_dict(item.get("statusDetailDisplay"))),
                "iconSource": str(item.get("iconSource") or ""),
            }
        )
    return linked


def resolve_activation_items(
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
    tool_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    refs = [str(item) for item in as_list(record.get("activationRefs")) if str(item)]
    if not refs:
        refs = [str(item) for item in as_list(record.get("capabilityRefs")) if str(item)]
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


def item_ready(item: dict[str, object]) -> bool:
    return not attention_status(str(item.get("status") or ""))


def status_payload(
    record: dict[str, object],
    activation_items: list[dict[str, object]],
) -> tuple[str, dict[str, str]]:
    missing_requirements = as_str(record.get("missingRequirements"))
    if missing_requirements:
        return "needs_setup", localized(
            f"缺失依赖：{missing_requirements}",
            f"Missing requirements: {missing_requirements}",
        )

    if activation_items:
        if all(item_ready(item) for item in activation_items):
            names = [
                as_str(as_dict(item.get("displayName")).get("zh"))
                or as_str(item.get("name"))
                for item in activation_items
            ]
            joined = "、".join(name for name in names if name)
            return "ready", localized(
                f"当前可直接配合 {joined} 使用。" if joined else STATUS_DISPLAY["ready"]["detail"]["zh"],
                f"Ready with {', '.join(name for name in names if name)}."
                if names
                else STATUS_DISPLAY["ready"]["detail"]["en"],
            )

        detail = next(
            (
                as_dict(item.get("statusDetailDisplay"))
                for item in activation_items
                if attention_status(str(item.get("status") or ""))
            ),
            {},
        )
        return "needs_setup", {
            "zh": as_str(detail.get("zh")) or STATUS_DISPLAY["needs_setup"]["detail"]["zh"],
            "en": as_str(detail.get("en")) or STATUS_DISPLAY["needs_setup"]["detail"]["en"],
        }

    return "instruction_only", dict(STATUS_DISPLAY["instruction_only"]["detail"])


def display_payload(record: dict[str, object]) -> dict[str, object]:
    display_name = as_str(record.get("displayName")) or as_str(record.get("name"))
    display_name_zh = as_str(record.get("displayNameZh")) or display_name
    summary = as_str(record.get("description")) or display_name
    detail_zh = as_str(record.get("displayDescriptionZh")) or summary
    return {
        "name": display_name,
        "nameZh": display_name_zh,
        "summary": summary,
        "detail": summary,
        "detailZh": detail_zh,
    }


def build_search_text(request: SearchTextRequest) -> str:
    return " ".join(
        [
            as_str(request.record.get("name")),
            as_str(request.display.get("name")),
            as_str(request.display.get("nameZh")),
            as_str(request.display.get("summary")),
            as_str(request.display.get("detailZh")),
            STATUS_DISPLAY[request.status]["label"]["en"],
            STATUS_DISPLAY[request.status]["label"]["zh"],
            request.status_detail_display["en"],
            request.status_detail_display["zh"],
            *request.example_prompts,
            *[as_str(item.get("id")) for item in request.linked_capabilities],
        ]
    ).lower()


def build_skill_item(
    *,
    record: dict[str, object],
    family_map: dict[str, dict[str, object]],
    tool_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    activation_items = resolve_activation_items(record, family_map, tool_map)
    linked = linked_capabilities(record, family_map)
    status, status_detail_display = status_payload(record, activation_items)
    section_key = "shadowed" if bool(record.get("shadowed")) else status
    display = display_payload(record)
    example_prompts = [str(item) for item in as_list(record.get("examplePrompts")) if str(item)]
    return {
        "id": as_str(record.get("id")),
        "name": as_str(record.get("name")),
        "source": as_str(record.get("source")),
        "displayName": localized(as_str(display.get("nameZh")), as_str(display.get("name"))),
        "displayNameText": as_str(display.get("name")),
        "displaySummary": localized(as_str(display.get("detailZh")), as_str(display.get("summary"))),
        "displayDetail": localized(as_str(display.get("detailZh")), as_str(display.get("detail"))),
        "description": as_str(display.get("summary")),
        "summary": as_str(display.get("summary")),
        "detail": as_str(display.get("detail")),
        "status": status,
        "statusLabel": localized(
            STATUS_DISPLAY[status]["label"]["zh"],
            STATUS_DISPLAY[status]["label"]["en"],
        ),
        "statusDetailDisplay": status_detail_display,
        "needsAttention": status != "ready",
        "shadowed": bool(record.get("shadowed")),
        "always": bool(record.get("always")),
        "missingRequirements": as_str(record.get("missingRequirements")),
        "path": as_str(record.get("path")),
        "canEdit": bool(record.get("canEdit")),
        "canDelete": bool(record.get("canDelete")),
        "iconSource": skill_icon_source(as_str(record.get("icon"), "book")),
        "category": as_str(record.get("category"), "general"),
        "sectionKey": section_key,
        "sectionTitle": dict(SECTION_TITLES[section_key]),
        "linkedCapabilities": linked,
        "linkedCapabilityRefs": [item["id"] for item in linked],
        "examplePrompts": example_prompts,
        "metadata": dict(as_dict(record.get("metadata"))),
        "searchText": build_search_text(
            SearchTextRequest(
                record=record,
                display=display,
                status=status,
                status_detail_display=status_detail_display,
                linked_capabilities=linked,
                example_prompts=example_prompts,
            )
        ),
    }
