from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from bao.session.state import (
    session_routing_metadata,
    session_runtime_state,
    session_view_state,
    session_workflow_state,
)


@dataclass(frozen=True)
class SidebarProjection:
    rows: list[dict[str, Any]]
    expanded_groups: dict[str, bool]
    unread_count: int
    unread_fingerprint: str


@dataclass(frozen=True)
class ActiveSessionProjection:
    key: str
    message_count: int | None
    has_messages: bool | None
    read_only: bool


def format_display_title(key: str, title: Any, *, natural_key: str = "desktop:local") -> str:
    if isinstance(title, str):
        cleaned = title.strip()
        if cleaned:
            return cleaned
    if key == natural_key:
        return "default"
    if "::" in key:
        _prefix, _sep, suffix = key.partition("::")
        if suffix:
            return suffix
    return key


def session_family_key(key: str) -> str:
    if "::" in key:
        prefix, _sep, _suffix = key.partition("::")
        return prefix
    return key


def session_channel_key(key: str) -> str:
    family = session_family_key(key)
    if ":" in family:
        prefix, _sep, _rest = family.partition(":")
        return prefix or "other"
    return family if family == "heartbeat" else "other"


def parse_updated_at(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw > 10_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return parse_updated_at(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def format_updated_label(updated: Any) -> str:
    dt = parse_updated_at(updated)
    if dt is None:
        return ""
    now = datetime.now(tz=dt.tzinfo)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    if seconds < 604800:
        return f"{seconds // 86400}d"
    if dt.year == now.year:
        return f"{dt.month}/{dt.day}"
    return f"{dt.year}/{dt.month}/{dt.day}"


def build_session_item(
    key: str,
    *,
    natural_key: str,
    updated_at: Any = "",
    channel: str = "desktop",
    has_unread: bool = False,
    title: Any = None,
    message_count: Any = None,
    has_messages: Any = None,
    session_kind: str = "regular",
    read_only: bool = False,
    parent_session_key: str = "",
    parent_title: str = "",
    child_status: str = "",
    is_running: bool = False,
    self_running: bool | None = None,
    needs_tail_backfill: bool = False,
) -> dict[str, Any]:
    normalized_count = (
        message_count if isinstance(message_count, int) and message_count >= 0 else None
    )
    normalized_has_messages = (
        has_messages
        if isinstance(has_messages, bool)
        else (normalized_count > 0 if normalized_count is not None else None)
    )
    running = bool(is_running)
    return {
        "key": key,
        "title": format_display_title(key, title, natural_key=natural_key),
        "updated_at": updated_at,
        "updated_label": format_updated_label(updated_at),
        "channel": channel,
        "has_unread": has_unread,
        "message_count": normalized_count,
        "has_messages": normalized_has_messages,
        "session_kind": session_kind,
        "is_read_only": read_only,
        "parent_session_key": parent_session_key,
        "parent_title": parent_title,
        "child_status": child_status,
        "is_running": running,
        "self_running": running if self_running is None else bool(self_running),
        "needs_tail_backfill": bool(needs_tail_backfill),
    }


def filter_session_dicts(raw_sessions: list[Any]) -> list[dict[str, Any]]:
    return [item for item in raw_sessions if isinstance(item, dict)]


def project_active_session(
    sessions: Iterable[dict[str, Any]],
    key: str,
) -> ActiveSessionProjection:
    for session in sessions:
        if str(session.get("key", "")) != key:
            continue
        message_count = session.get("message_count")
        has_messages = session.get("has_messages")
        return ActiveSessionProjection(
            key=key,
            message_count=message_count if isinstance(message_count, int) and message_count >= 0 else None,
            has_messages=has_messages if isinstance(has_messages, bool) else None,
            read_only=bool(session.get("is_read_only", False)),
        )
    return ActiveSessionProjection(
        key=key,
        message_count=None,
        has_messages=None,
        read_only=False,
    )


def visible_session_key(
    candidates: tuple[str, ...],
    *,
    available_keys: set[str],
    pending_create_keys: set[str],
) -> str:
    for candidate in candidates:
        if candidate and (candidate in pending_create_keys or candidate in available_keys):
            return candidate
    return ""


def visible_session_key_for_channel(
    candidates: tuple[str, ...],
    *,
    available_keys: set[str],
    pending_create_keys: set[str],
    channel: str,
) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        if candidate not in pending_create_keys and candidate not in available_keys:
            continue
        if session_channel_key(candidate) != channel:
            continue
        return candidate
    return ""


def session_sort_value(item: dict[str, Any]) -> tuple[int, float | str, str]:
    updated_at = item.get("updated_at", "")
    if isinstance(updated_at, (int, float)):
        base: tuple[int, float | str] = (2, float(updated_at))
    elif isinstance(updated_at, str) and updated_at:
        base = (1, updated_at)
    else:
        base = (0, "")
    key = str(item.get("key", "") or "")
    return base[0], base[1], key


def sidebar_channel_sort_key(channel: str) -> tuple[int, str]:
    if channel == "desktop":
        return (0, channel)
    if channel == "heartbeat":
        return (2, channel)
    return (1, channel)


def visible_sidebar_items(
    items: list[dict[str, Any]], *, expanded: bool, active_key: str
) -> list[dict[str, Any]]:
    if expanded:
        return items
    if not active_key:
        return []
    return [item for item in items if str(item.get("key", "")) == active_key]


def title_by_key(sessions: Iterable[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item.get("key", "")): str(item.get("title", "") or item.get("key", ""))
        for item in sessions
        if str(item.get("key", ""))
    }


def running_parent_keys(sessions: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("parent_session_key", ""))
        for item in sessions
        if str(item.get("child_status", "")) == "running"
        and str(item.get("parent_session_key", ""))
    }


def project_session_item(
    session: dict[str, Any],
    *,
    natural_key: str,
    current_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    key = str(session.get("key") or "")
    routing_payload = session.get("routing") if isinstance(session.get("routing"), dict) else {}
    runtime_payload = session.get("runtime") if isinstance(session.get("runtime"), dict) else {}
    workflow_payload = session.get("workflow") if isinstance(session.get("workflow"), dict) else {}
    view_payload = session.get("view") if isinstance(session.get("view"), dict) else {}
    if not (routing_payload and runtime_payload and workflow_payload and view_payload):
        raise ValueError(f"session entry missing structured snapshot fields: {key}")
    routing = session_routing_metadata({"routing": routing_payload})
    runtime = session_runtime_state(runtime_payload)
    workflow = session_workflow_state({"workflow": workflow_payload})
    view = session_view_state({"view": view_payload})
    child_status = workflow.child_outcome.status or ("running" if runtime.child_running else "")
    has_unread = view.read_receipts.has_unread_ai
    title = view.title
    channel = (
        session_channel_key(routing.parent_session_key)
        if routing.session_kind == "subagent_child" and routing.parent_session_key
        else session_channel_key(key)
    )
    parent_title = ""
    if routing.parent_session_key:
        for item in current_sessions or []:
            if str(item.get("key", "")) != routing.parent_session_key:
                continue
            parent_title = str(item.get("title", "") or routing.parent_session_key)
            break
    return build_session_item(
        key,
        natural_key=natural_key,
        updated_at=session.get("updated_at", ""),
        channel=channel,
        has_unread=has_unread,
        title=title,
        message_count=session.get("message_count"),
        has_messages=session.get("has_messages"),
        session_kind=routing.session_kind,
        read_only=routing.read_only,
        parent_session_key=routing.parent_session_key,
        parent_title=parent_title,
        child_status=child_status,
        is_running=runtime.is_running,
        self_running=runtime.is_running,
        needs_tail_backfill=bool(session.get("needs_tail_backfill", False)),
    )


def normalize_session_item(
    session: dict[str, Any],
    *,
    title_index: dict[str, str],
    running_parent_index: set[str],
) -> dict[str, Any]:
    normalized = dict(session)
    key = str(normalized.get("key", ""))
    parent_key = str(normalized.get("parent_session_key", "") or "")
    normalized["parent_title"] = title_index.get(parent_key, "")
    self_running = bool(normalized.get("self_running", normalized.get("is_running", False)))
    normalized["is_running"] = self_running or key in running_parent_index
    return normalized


def normalize_session_items(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    title_index = title_by_key(sessions)
    running_parent_index = running_parent_keys(sessions)
    return [
        normalize_session_item(
            session,
            title_index=title_index,
            running_parent_index=running_parent_index,
        )
        for session in sessions
    ]


def tail_backfill_keys(sessions: Iterable[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for item in sessions:
        if not bool(item.get("needs_tail_backfill", False)):
            continue
        key = str(item.get("key", "")).strip()
        if key:
            keys.append(key)
    return keys


def pick_latest_key(sessions: list[dict[str, Any]], *, preferred_channel: str) -> str:
    preferred = [s for s in sessions if str(s.get("channel", "")) == preferred_channel]
    candidates = preferred if preferred else sessions
    if not candidates:
        return ""
    sort_values = [session_sort_value(s)[:2] for s in candidates]
    if not any(value[0] > 0 for value in sort_values):
        return str(candidates[0].get("key", "") or "")
    if len(set(sort_values)) == 1:
        return str(candidates[0].get("key", "") or "")
    best = max(candidates, key=session_sort_value)
    return str(best.get("key", "") or "")


def sidebar_channel_items(
    sessions: list[dict[str, Any]], *, active_key: str
) -> tuple[dict[str, list[dict[str, Any]]], list[str], list[str]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    unread_fingerprint_parts: list[str] = []
    for session in sessions:
        key = str(session.get("key", ""))
        channel = str(session.get("channel", "other") or "other")
        if channel not in groups:
            groups[channel] = []
            order.append(channel)
        has_unread = bool(session.get("has_unread", False)) and key != active_key
        groups[channel].append(
            {
                "key": key,
                "title": str(session.get("title", "") or key),
                "channel": channel,
                "visual_channel": str(
                    session.get(
                        "visual_channel",
                        "subagent"
                        if str(session.get("session_kind", "regular") or "regular")
                        == "subagent_child"
                        else channel,
                    )
                    or channel
                ),
                "has_unread": has_unread,
                "updated_text": str(session.get("updated_label", "") or ""),
                "is_read_only": bool(session.get("is_read_only", False)),
                "is_running": bool(session.get("is_running", False)),
                "parent_session_key": str(session.get("parent_session_key", "") or ""),
                "is_child_session": str(session.get("session_kind", "regular") or "regular")
                == "subagent_child",
            }
        )
        if has_unread:
            unread_fingerprint_parts.append(key)
    order.sort(key=sidebar_channel_sort_key)
    return groups, order, unread_fingerprint_parts


def initial_sidebar_group_expanded(
    channel: str,
    items: list[dict[str, Any]],
    *,
    active_key: str,
) -> bool:
    if active_key and any(str(item.get("key", "")) == active_key for item in items):
        return True
    if active_key:
        return False
    return channel == "desktop"


def build_sidebar_rows_for_channel(
    channel: str,
    items: list[dict[str, Any]],
    *,
    active_key: str,
    expanded: bool,
) -> list[dict[str, Any]]:
    child_buckets: dict[str, list[dict[str, Any]]] = {}
    child_remainder: list[dict[str, Any]] = []
    reordered_items: list[dict[str, Any]] = []
    for item in items:
        if bool(item.get("is_child_session", False)) and str(item.get("parent_session_key", "")):
            parent_key = str(item.get("parent_session_key", ""))
            child_buckets.setdefault(parent_key, []).append(item)
        elif bool(item.get("is_child_session", False)):
            child_remainder.append(item)
    for item in items:
        if bool(item.get("is_child_session", False)):
            continue
        reordered_items.append(item)
        reordered_items.extend(child_buckets.get(str(item.get("key", "")), []))
    reordered_items.extend(child_remainder)
    unread_in_group = sum(1 for item in reordered_items if bool(item.get("has_unread", False)))
    group_has_running = any(bool(item.get("is_running", False)) for item in reordered_items)
    rows = [
        {
            "row_id": f"header:{channel}",
            "is_header": True,
            "channel": channel,
            "expanded": expanded,
            "item_key": "",
            "item_title": "",
            "item_updated_text": "",
            "visual_channel": channel,
            "is_read_only": False,
            "is_running": False,
            "is_child_session": False,
            "parent_session_key": "",
            "item_has_unread": False,
            "item_count": len(reordered_items),
            "group_unread_count": unread_in_group,
            "group_has_running": group_has_running,
            "is_last_in_group": False,
            "is_first_in_group": False,
        }
    ]
    visible_items = visible_sidebar_items(
        reordered_items,
        expanded=expanded,
        active_key=active_key,
    )
    for index, item in enumerate(visible_items):
        rows.append(
            {
                "row_id": f"session:{item.get('key', '')}",
                "is_header": False,
                "channel": channel,
                "expanded": False,
                "item_key": str(item.get("key", "")),
                "item_title": str(item.get("title", "") or item.get("key", "")),
                "item_updated_text": str(item.get("updated_text", "") or ""),
                "visual_channel": str(item.get("visual_channel", channel) or channel),
                "is_read_only": bool(item.get("is_read_only", False)),
                "is_running": bool(item.get("is_running", False)),
                "is_child_session": bool(item.get("is_child_session", False)),
                "parent_session_key": str(item.get("parent_session_key", "") or ""),
                "item_has_unread": bool(item.get("has_unread", False)),
                "item_count": 0,
                "group_unread_count": 0,
                "group_has_running": False,
                "is_last_in_group": index == len(visible_items) - 1,
                "is_first_in_group": index == 0,
            }
        )
    return rows


def pin_sidebar_active_row(
    rows: list[dict[str, Any]],
    *,
    active_key: str,
    current_rows: list[dict[str, Any]],
) -> None:
    if not active_key:
        return
    current_active_index = next(
        (
            index
            for index, row in enumerate(current_rows)
            if str(row.get("row_id", "")) == f"session:{active_key}"
        ),
        -1,
    )
    if current_active_index < 0 or current_active_index >= len(current_rows):
        return
    current_active_row = current_rows[current_active_index]
    active_channel = str(current_active_row.get("channel", "") or "")
    if not active_channel:
        return
    session_slot = 0
    for index in range(current_active_index - 1, -1, -1):
        row = current_rows[index]
        if str(row.get("channel", "") or "") != active_channel:
            continue
        if bool(row.get("is_header", False)):
            break
        session_slot += 1
    next_active_index = next(
        (index for index, row in enumerate(rows) if str(row.get("item_key", "")) == active_key),
        -1,
    )
    if next_active_index < 0 or next_active_index == current_active_index:
        return
    pinned_row = rows.pop(next_active_index)
    header_index = -1
    session_count = 0
    for index, row in enumerate(rows):
        if str(row.get("channel", "") or "") != active_channel:
            continue
        if bool(row.get("is_header", False)):
            header_index = index
            continue
        if header_index >= 0:
            session_count += 1
    if header_index < 0:
        rows.insert(max(0, min(current_active_index, len(rows))), pinned_row)
        return
    target_index = header_index + 1 + min(session_slot, session_count)
    rows.insert(target_index, pinned_row)


def build_sidebar_projection(
    sessions: list[dict[str, Any]],
    *,
    active_key: str,
    expanded_groups: dict[str, bool],
    current_rows: list[dict[str, Any]] | None = None,
    channels: set[str] | None = None,
) -> SidebarProjection:
    groups, order, unread_fingerprint_parts = sidebar_channel_items(sessions, active_key=active_key)
    available_channels = set(groups.keys())
    next_expanded_groups = {
        channel: expanded for channel, expanded in expanded_groups.items() if channel in available_channels
    }
    for channel in order:
        if channel not in next_expanded_groups:
            next_expanded_groups[channel] = initial_sidebar_group_expanded(
                channel,
                groups[channel],
                active_key=active_key,
            )
    previous_rows = [dict(row) for row in current_rows or []]
    if channels is None or not previous_rows:
        rows: list[dict[str, Any]] = []
        for channel in order:
            rows.extend(
                build_sidebar_rows_for_channel(
                    channel,
                    groups[channel],
                    active_key=active_key,
                    expanded=next_expanded_groups[channel],
                )
            )
    else:
        existing_rows: dict[str, list[dict[str, Any]]] = {}
        for row in previous_rows:
            channel = str(row.get("channel", "other") or "other")
            if channel not in available_channels and channel not in channels:
                continue
            existing_rows.setdefault(channel, []).append(dict(row))
        rows = []
        for channel in order:
            if channel in channels:
                rows.extend(
                    build_sidebar_rows_for_channel(
                        channel,
                        groups[channel],
                        active_key=active_key,
                        expanded=next_expanded_groups[channel],
                    )
                )
                continue
            rows.extend(existing_rows.get(channel, []))
    pin_sidebar_active_row(rows, active_key=active_key, current_rows=previous_rows)
    unread_fingerprint_parts.sort()
    return SidebarProjection(
        rows=rows,
        expanded_groups=next_expanded_groups,
        unread_count=len(unread_fingerprint_parts),
        unread_fingerprint="|".join(unread_fingerprint_parts),
    )
