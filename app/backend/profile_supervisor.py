from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.cron import _serialize_job
from app.backend.session_projection import normalize_session_items, project_session_item
from bao.cron.service import CronService
from bao.profile import (
    ProfileContext,
    ProfileSpec,
    ensure_profile_registry,
    legacy_profile_id,
    profile_context,
    profile_context_from_mapping,
    rewrite_profile_scoped_id,
)

_SNAPSHOT_FILENAME = "supervisor_snapshot.json"
_SNAPSHOT_SCHEMA_VERSION = 1
_NATURAL_KEY = "desktop:local"
_RECENT_COMPLETED_WINDOW_SECONDS = 2 * 60 * 60
_RECENT_COMPLETED_LIMIT = 8
_COLLECTION_NAMES = ("working", "completed", "automation", "attention")
_SNAPSHOT_ITEM_SECTIONS = (
    ("working", "id"),
    ("automation", "id"),
    ("completed", "id"),
    ("attention", "id"),
    ("workers", "workerId"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return _coerce_dt(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _relative_time(value: object) -> str:
    dt = _coerce_dt(value)
    if dt is None:
        return ""
    now = datetime.now(dt.tzinfo or timezone.utc)
    seconds = int((dt - now).total_seconds())
    future = seconds > 0
    distance = abs(seconds)
    if distance < 60:
        if future:
            return "稍后"
        return "刚刚"
    if distance < 3600:
        minutes = max(1, distance // 60)
        return f"{minutes} 分钟后" if future else f"{minutes} 分钟前"
    if distance < 86400:
        hours = max(1, distance // 3600)
        return f"{hours} 小时后" if future else f"{hours} 小时前"
    if distance < 2592000:
        days = max(1, distance // 86400)
        return f"{days} 天后" if future else f"{days} 天前"
    if distance < 31536000:
        months = max(1, distance // 2592000)
        return f"{months} 个月后" if future else f"{months} 个月前"
    years = max(1, distance // 31536000)
    return f"{years} 年后" if future else f"{years} 年前"


def _safe_text(value: object, *, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _clone_dict_list(values: list[object]) -> list[dict[str, Any]]:
    return [dict(item) for item in values if isinstance(item, dict)]


def _empty_projection() -> dict[str, Any]:
    return {
        "overview": {},
        "profiles": [],
        **{name: [] for name in _COLLECTION_NAMES},
    }


def _filter_recent_completed_items(
    items: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    recent: list[dict[str, Any]] = []
    for item in items:
        dt = _coerce_dt(item.get("updatedAt") or item.get("updated_at") or item.get("lastRunAt"))
        if dt is None:
            continue
        age_seconds = (current - dt).total_seconds()
        if age_seconds < 0:
            age_seconds = 0
        if age_seconds > _RECENT_COMPLETED_WINDOW_SECONDS:
            continue
        recent.append(dict(item))
    recent.sort(key=lambda item: str(item.get("updatedAt", "") or ""), reverse=True)
    return recent[:_RECENT_COMPLETED_LIMIT]


def _avatar_source(avatar_key: str) -> str:
    key = str(avatar_key or "mochi").strip() or "mochi"
    return f"../resources/profile-avatars/{key}.svg"


def _icon_source(name: str) -> str:
    return f"../resources/icons/{name}.svg"


def _channel_icon_source(channel: str) -> str:
    normalized = str(channel or "").strip().lower()
    if normalized in {
        "telegram",
        "discord",
        "whatsapp",
        "feishu",
        "slack",
        "qq",
        "dingtalk",
        "imessage",
    }:
        return f"../resources/icons/channel-{normalized}.svg"
    if normalized == "desktop":
        return _icon_source("sidebar-monitor")
    if normalized == "subagent":
        return _icon_source("sidebar-subagent")
    if normalized == "heartbeat":
        return _icon_source("sidebar-heartbeat")
    if normalized == "cron":
        return _icon_source("sidebar-cron")
    if normalized == "system":
        return _icon_source("sidebar-system")
    if normalized == "email":
        return _icon_source("sidebar-mail")
    return _icon_source("sidebar-chat")


def _glyph_for_kind(kind: str, channel: str) -> str:
    if kind == "subagent_task":
        return _icon_source("sidebar-subagent")
    if kind == "cron_job":
        return _icon_source("sidebar-cron")
    if kind == "heartbeat_check":
        return _icon_source("sidebar-heartbeat")
    if kind == "issue":
        return _icon_source("sidebar-pulse")
    return _channel_icon_source(channel)


def _snapshot_path(context: ProfileContext) -> Path:
    return context.state_root / _SNAPSHOT_FILENAME


def _read_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _item_legacy_profile_id(
    item: dict[str, Any],
    *,
    snapshot_profile_id: str,
    profile_id: str,
) -> str:
    return legacy_profile_id(
        current_profile_id=profile_id,
        item_profile_id=item.get("profileId", ""),
        snapshot_profile_id=snapshot_profile_id,
    )


def _normalize_snapshot_route_value(
    item: dict[str, Any],
    *,
    snapshot_profile_id: str,
    profile_id: str,
) -> bool:
    if str(item.get("routeKind", "") or "") != "profile":
        return False
    route_value = str(item.get("routeValue", "") or "").strip()
    if not route_value or route_value == profile_id:
        return False
    legacy_profile_id = _item_legacy_profile_id(
        item,
        snapshot_profile_id=snapshot_profile_id,
        profile_id=profile_id,
    )
    if route_value != legacy_profile_id:
        return False
    item["routeValue"] = profile_id
    return True


def _normalize_snapshot_items(
    values: list[object],
    *,
    id_key: str,
    snapshot_profile_id: str,
    profile_id: str,
) -> tuple[list[dict[str, Any]], bool]:
    items: list[dict[str, Any]] = []
    changed = False
    for value in values:
        if not isinstance(value, dict):
            continue
        item = dict(value)
        legacy_profile_id = _item_legacy_profile_id(
            item,
            snapshot_profile_id=snapshot_profile_id,
            profile_id=profile_id,
        )
        item_profile_id = str(item.get("profileId", "") or "").strip()
        if item_profile_id != profile_id:
            item["profileId"] = profile_id
            changed = True
        if legacy_profile_id:
            current_id = str(item.get(id_key, "") or "").strip()
            next_id = rewrite_profile_scoped_id(
                current_id,
                legacy_profile_id=legacy_profile_id,
                profile_id=profile_id,
            )
            if next_id != current_id:
                item[id_key] = next_id
                changed = True
        if _normalize_snapshot_route_value(
            item,
            snapshot_profile_id=snapshot_profile_id,
            profile_id=profile_id,
        ):
            changed = True
        items.append(item)
    return items, changed


def _normalize_snapshot_payload(
    payload: dict[str, Any],
    *,
    profile_id: str,
) -> tuple[dict[str, Any], bool]:
    if not payload:
        return {}, False
    snapshot = dict(payload)
    snapshot_profile_id = str(snapshot.get("profile_id", "") or "").strip()
    changed = False
    if snapshot_profile_id != profile_id:
        snapshot["profile_id"] = profile_id
        changed = True
    for section_name, id_key in _SNAPSHOT_ITEM_SECTIONS:
        next_items, section_changed = _normalize_snapshot_items(
            list(snapshot.get(section_name, []) or []),
            id_key=id_key,
            snapshot_profile_id=snapshot_profile_id,
            profile_id=profile_id,
        )
        snapshot[section_name] = next_items
        changed = changed or section_changed
    return snapshot, changed


def _load_sessions_from_root(state_root: Path) -> list[dict[str, Any]]:
    from bao.session.manager import SessionManager

    session_manager = SessionManager(state_root)
    try:
        raw_sessions = session_manager.list_sessions()
    finally:
        session_manager.close()
    projected = [
        project_session_item(
            session,
            natural_key=_NATURAL_KEY,
            current_sessions=[],
        )
        for session in raw_sessions
    ]
    return normalize_session_items(projected)


def _load_cron_items(cron_store_path: Path) -> list[dict[str, Any]]:
    cron_service = CronService(cron_store_path)
    store = cron_service._load_store()
    return [_serialize_job(job, "zh") for job in store.jobs]


def _heartbeat_static_snapshot(heartbeat_file: Path) -> dict[str, Any]:
    return {
        "enabled": heartbeat_file.exists(),
        "running": False,
        "heartbeat_file": str(heartbeat_file),
        "heartbeat_file_exists": heartbeat_file.exists(),
        "last_checked_at_ms": None,
        "last_run_at_ms": None,
        "last_decision": "",
        "last_error": "",
    }


def _status_label(key: str) -> str:
    if key == "running":
        return "运行中"
    if key == "completed":
        return "已完成"
    if key == "failed":
        return "失败"
    if key == "scheduled":
        return "已调度"
    if key == "disabled":
        return "已停用"
    if key == "error":
        return "异常"
    return "待命"


def _is_gateway_live(state: str) -> bool:
    return state in {"running", "starting"}


def _channel_key(value: object) -> str:
    return str(value or "").strip().lower()


_PROFILE_CHANNEL_KEYS = {
    "desktop",
    "telegram",
    "discord",
    "whatsapp",
    "feishu",
    "slack",
    "qq",
    "dingtalk",
    "imessage",
    "email",
}


def _dedupe_channel_keys(values: list[object]) -> list[str]:
    keys: list[str] = []
    for value in values:
        key = _channel_key(value)
        if key and key in _PROFILE_CHANNEL_KEYS and key not in keys:
            keys.append(key)
    return keys


def _gateway_channel_keys(items: list[object]) -> list[str]:
    keys: list[object] = []
    for item in items:
        if isinstance(item, dict):
            keys.append(
                item.get("channel")
                or item.get("key")
                or item.get("id")
                or item.get("name")
                or item.get("label")
            )
            continue
        keys.append(item)
    return _dedupe_channel_keys(keys)


def _primary_visual_channel(channel_keys: list[object]) -> str:
    keys = _dedupe_channel_keys(channel_keys)
    for key in keys:
        if key != "desktop":
            return key
    return keys[0] if keys else "desktop"


def _session_inventory(
    sessions: list[dict[str, Any]],
    *,
    gateway_channels: list[object] | None = None,
) -> dict[str, Any]:
    total_session_count = 0
    total_child_session_count = 0
    channel_keys = _gateway_channel_keys(gateway_channels or [])
    for item in sessions:
        kind = str(item.get("kind", "") or "")
        is_child = bool(item.get("is_child_session", item.get("isChildSession", False))) or kind == "subagent_task"
        session_key = str(item.get("key", item.get("sessionKey", "")) or "")
        if is_child:
            total_child_session_count += 1
        elif session_key or kind == "session_reply":
            total_session_count += 1
        channel = (
            item.get("visual_channel")
            or item.get("visualChannel")
            or item.get("channel")
            or item.get("accentKey")
        )
        channel_keys = _dedupe_channel_keys([*channel_keys, channel])
    return {
        "totalSessionCount": total_session_count,
        "totalChildSessionCount": total_child_session_count,
        "channelKeys": channel_keys[:4],
    }


def _session_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    session_reply_count = 0
    subagent_count = 0
    channels: list[str] = []
    for item in items:
        kind = str(item.get("kind", "") or "")
        if kind == "session_reply":
            session_reply_count += 1
        elif kind == "subagent_task":
            subagent_count += 1
        channel = str(item.get("visualChannel", "") or "")
        if channel and channel not in channels:
            channels.append(channel)
    return {
        "sessionReplyCount": session_reply_count,
        "subagentCount": subagent_count,
        "channelKeys": channels[:3],
    }


def _automation_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    running_count = 0
    for item in items:
        if bool(item.get("isRunning", False)):
            running_count += 1
    return {"runningAutomationCount": running_count}


def _profile_status_summary(
    *,
    is_active: bool,
    is_live: bool,
    session_reply_count: int,
    subagent_count: int,
    other_working_count: int,
    automation_count: int,
    total_session_count: int,
    total_child_session_count: int,
) -> str:
    if is_active and is_live:
        if session_reply_count or subagent_count:
            parts: list[str] = []
            if session_reply_count:
                parts.append(f"{session_reply_count} 个会话")
            if subagent_count:
                parts.append(f"{subagent_count} 个子代理")
            return " / ".join(parts) + " 工作中"
        if other_working_count:
            return f"{other_working_count} 项工作进行中"
        if automation_count:
            return f"{automation_count} 个自动化待命"
        return "当前分身空闲"
    if is_active:
        if automation_count:
            return f"网关未启动 · {automation_count} 个自动化待命"
        return "网关未启动"
    if automation_count:
        return f"{automation_count} 个自动化待命"
    parts: list[str] = []
    if total_session_count:
        parts.append(f"{total_session_count} 个会话")
    if total_child_session_count:
        parts.append(f"{total_child_session_count} 个子代理")
    if parts:
        return " / ".join(parts)
    return "当前空闲"


def _task_time_label(task: dict[str, Any]) -> str:
    for value in (
        task.get("next_run_at_ms"),
        task.get("next_run_text"),
        task.get("last_run_at_ms"),
        task.get("updated_at_ms"),
    ):
        label = _relative_time(value)
        if label:
            return label
    return ""


def _build_worker_token(
    *,
    profile_id: str,
    avatar_source: str,
    title: str,
    variant: str,
    accent_key: str,
    glyph_source: str,
    status_key: str,
    status_label: str,
    route_kind: str,
    route_value: str,
    unit_id: str,
) -> dict[str, Any]:
    return {
        "workerId": unit_id,
        "profileId": profile_id,
        "avatarSource": avatar_source,
        "title": title,
        "variant": variant,
        "accentKey": accent_key,
        "glyphSource": glyph_source,
        "statusKey": status_key,
        "statusLabel": status_label,
        "routeKind": route_kind,
        "routeValue": route_value,
    }


def _build_profile_card(
    *,
    spec: ProfileSpec,
    avatar_source: str,
    is_active: bool,
    updated_at: str,
    live_label: str,
    snapshot_label: str,
    status_summary: str,
    working_count: int,
    automation_count: int,
    attention_count: int,
    inventory: dict[str, Any],
    session_reply_count: int,
    subagent_count: int,
    running_automation_count: int,
    gateway_state: str,
    gateway_detail: str,
    is_gateway_live: bool,
    workers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": spec.id,
        "displayName": spec.display_name,
        "avatarKey": spec.avatar_key,
        "avatarSource": avatar_source,
        "isActive": is_active,
        "isLive": is_active,
        "liveLabel": live_label,
        "snapshotLabel": snapshot_label,
        "updatedAt": updated_at,
        "updatedLabel": _relative_time(updated_at),
        "statusSummary": status_summary,
        "workingCount": working_count,
        "automationCount": automation_count,
        "attentionCount": attention_count,
        "totalSessionCount": int(inventory["totalSessionCount"]),
        "totalChildSessionCount": int(inventory["totalChildSessionCount"]),
        "sessionReplyCount": session_reply_count,
        "subagentCount": subagent_count,
        "runningAutomationCount": running_automation_count,
        "channelKeys": list(inventory["channelKeys"]),
        "gatewayState": gateway_state,
        "gatewayDetail": gateway_detail,
        "isGatewayLive": is_gateway_live,
        "workers": workers[:8],
    }


def _session_summary(item: dict[str, Any]) -> str:
    if bool(item.get("is_running", False)):
        if bool(item.get("is_child_session", False)):
            return "长任务中"
        return "回复中"
    child_status = str(item.get("child_status", "") or "")
    if child_status == "completed":
        return "已完成"
    if child_status == "failed":
        return "已失败"
    if child_status == "cancelled":
        return "已取消"
    return "最近会话"


def _build_session_work_units(
    *,
    profile_id: str,
    avatar_source: str,
    sessions: list[dict[str, Any]],
    is_live: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    units: list[dict[str, Any]] = []
    workers: list[dict[str, Any]] = []
    ordered_sessions = sorted(
        [dict(item) for item in sessions],
        key=lambda item: (
            bool(item.get("is_running", False)),
            str(item.get("updated_at", "") or ""),
        ),
        reverse=True,
    )
    for session in ordered_sessions:
        key = str(session.get("key", "") or "")
        if not key:
            continue
        is_child = bool(session.get("is_child_session", False))
        kind = "subagent_task" if is_child else "session_reply"
        status_key = (
            "running"
            if bool(session.get("is_running", False))
            else str(session.get("child_status", "") or "idle")
        )
        unit_id = f"{profile_id}:{kind}:{key}"
        accent_key = str(session.get("visual_channel", session.get("channel", "desktop")) or "desktop")
        title = str(session.get("title", "") or key)
        unit = {
            "id": unit_id,
            "profileId": profile_id,
            "kind": kind,
            "title": title,
            "summary": _session_summary(session),
            "sessionKey": key,
            "parentSessionKey": str(session.get("parent_session_key", "") or ""),
            "visualChannel": accent_key,
            "accentKey": "subagent" if is_child else accent_key,
            "glyphSource": _glyph_for_kind(kind, accent_key),
            "statusKey": status_key or "idle",
            "statusLabel": _status_label(status_key or "idle"),
            "updatedAt": str(session.get("updated_at", "") or ""),
            "updatedLabel": str(session.get("updated_label", "") or ""),
            "relativeLabel": str(session.get("updated_label", "") or ""),
            "isLive": is_live,
            "personaVariant": "mini" if is_child else "primary",
            "avatarSource": avatar_source,
            "routeKind": "session",
            "routeValue": key,
            "canOpen": True,
            "canToggleCron": False,
            "canRunHeartbeat": False,
            "isRunning": bool(session.get("is_running", False)),
        }
        units.append(unit)
        workers.append(
            _build_worker_token(
                profile_id=profile_id,
                avatar_source=avatar_source,
                title=title,
                variant="mini" if is_child else "primary",
                accent_key="subagent" if is_child else accent_key,
                glyph_source=_glyph_for_kind(kind, accent_key),
                status_key=unit["statusKey"],
                status_label=unit["statusLabel"],
                route_kind="session",
                route_value=key,
                unit_id=unit_id,
            )
        )
    return units, workers


def _build_cron_work_units(
    *,
    profile_id: str,
    avatar_source: str,
    cron_items: list[dict[str, Any]],
    is_live: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    units: list[dict[str, Any]] = []
    workers: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for task in cron_items:
        task_id = str(task.get("id", "") or "")
        if not task_id:
            continue
        status_key = str(task.get("status_key", "draft") or "draft")
        title = str(task.get("name", "") or "未命名任务")
        summary = str(task.get("schedule_summary", "") or "自动化任务")
        time_label = _task_time_label(task)
        unit_id = f"{profile_id}:cron:{task_id}"
        unit = {
            "id": unit_id,
            "profileId": profile_id,
            "kind": "cron_job",
            "title": title,
            "summary": summary,
            "sessionKey": str(task.get("session_key", "") or ""),
            "visualChannel": "cron",
            "accentKey": "cron",
            "glyphSource": _glyph_for_kind("cron_job", "cron"),
            "statusKey": status_key,
            "statusLabel": str(task.get("status_label", "") or _status_label(status_key)),
            "updatedAt": str(task.get("updated_at_ms", "") or ""),
            "updatedLabel": time_label,
            "relativeLabel": time_label,
            "isLive": is_live,
            "personaVariant": "automation",
            "avatarSource": avatar_source,
            "routeKind": "cron",
            "routeValue": task_id,
            "canOpen": True,
            "canToggleCron": True,
            "canRunHeartbeat": False,
            "enabled": bool(task.get("enabled", False)),
            "isRunning": False,
        }
        units.append(unit)
        workers.append(
            _build_worker_token(
                profile_id=profile_id,
                avatar_source=avatar_source,
                title=title,
                variant="automation",
                accent_key="cron",
                glyph_source=_glyph_for_kind("cron_job", "cron"),
                status_key=status_key,
                status_label=unit["statusLabel"],
                route_kind="cron",
                route_value=task_id,
                unit_id=unit_id,
            )
        )
        if status_key == "error":
            issues.append(
                {
                    "id": f"{unit_id}:issue",
                    "profileId": profile_id,
                    "kind": "issue",
                    "title": title,
                    "summary": str(task.get("last_error", "") or "定时任务异常"),
                    "statusKey": "error",
                    "statusLabel": "待处理",
                    "visualChannel": "cron",
                    "accentKey": "cron",
                    "glyphSource": _glyph_for_kind("issue", "cron"),
                    "updatedAt": str(task.get("updated_at_ms", "") or ""),
                    "updatedLabel": time_label,
                    "relativeLabel": time_label,
                    "isLive": is_live,
                    "personaVariant": "automation",
                    "avatarSource": avatar_source,
                    "routeKind": "cron",
                    "routeValue": task_id,
                    "canOpen": True,
                    "canToggleCron": True,
                    "canRunHeartbeat": False,
                }
            )
    return units, workers, issues


def _build_heartbeat_work_unit(
    *,
    profile_id: str,
    avatar_source: str,
    heartbeat_status: dict[str, Any],
    is_live: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    enabled = bool(heartbeat_status.get("enabled", False))
    exists = bool(heartbeat_status.get("heartbeat_file_exists", False))
    if not enabled and not exists:
        return None, None
    status_key = "running" if bool(heartbeat_status.get("running", False)) else "idle"
    last_error = str(heartbeat_status.get("last_error", "") or "")
    if last_error:
        status_key = "error"
    unit = {
        "id": f"{profile_id}:heartbeat",
        "profileId": profile_id,
        "kind": "heartbeat_check",
        "title": "自动检查",
        "summary": (
            last_error
            or (
                "缺少检查说明"
                if not exists
                else (
                    f"上次检查 {_relative_time(heartbeat_status.get('last_checked_at_ms'))}"
                    if heartbeat_status.get("last_checked_at_ms")
                    else "待首次执行"
                )
            )
        ),
        "sessionKey": "heartbeat",
        "visualChannel": "heartbeat",
        "accentKey": "heartbeat",
        "glyphSource": _glyph_for_kind("heartbeat_check", "heartbeat"),
        "statusKey": status_key,
        "statusLabel": _status_label(status_key),
        "updatedAt": (
            str(heartbeat_status.get("updated_at", "") or "")
            or str(heartbeat_status.get("last_checked_at_ms", "") or "")
        ),
        "updatedLabel": _relative_time(heartbeat_status.get("last_checked_at_ms")),
        "relativeLabel": _relative_time(heartbeat_status.get("last_run_at_ms")),
        "isLive": is_live,
        "personaVariant": "automation",
        "avatarSource": avatar_source,
        "routeKind": "heartbeat",
        "routeValue": "heartbeat",
        "canOpen": True,
        "canToggleCron": False,
        "canRunHeartbeat": is_live,
        "enabled": enabled,
        "isRunning": status_key == "running",
    }
    issue = None
    if last_error or not exists:
        issue = {
            "id": f"{profile_id}:heartbeat:issue",
            "profileId": profile_id,
            "kind": "issue",
            "title": "自动检查",
            "summary": last_error or "缺少检查说明",
            "statusKey": "error",
            "statusLabel": "待处理",
            "visualChannel": "heartbeat",
            "accentKey": "heartbeat",
            "glyphSource": _glyph_for_kind("issue", "heartbeat"),
            "updatedAt": str(heartbeat_status.get("updated_at", "") or ""),
            "updatedLabel": unit["updatedLabel"],
            "relativeLabel": unit["relativeLabel"],
            "isLive": is_live,
            "personaVariant": "automation",
            "avatarSource": avatar_source,
            "routeKind": "heartbeat",
            "routeValue": "heartbeat",
            "canOpen": True,
            "canToggleCron": False,
            "canRunHeartbeat": is_live,
        }
    return unit, issue


def _build_gateway_issue(
    *,
    profile_id: str,
    avatar_source: str,
    gateway_state: str,
    gateway_detail: str,
    gateway_error: str,
    gateway_detail_is_error: bool,
    is_live: bool,
) -> dict[str, Any] | None:
    if gateway_state != "error" and not gateway_error and not gateway_detail_is_error:
        return None
    return {
        "id": f"{profile_id}:gateway:issue",
        "profileId": profile_id,
        "kind": "issue",
        "title": "网关状态",
        "summary": gateway_error or gateway_detail or "网关异常",
        "statusKey": "error",
        "statusLabel": "待处理",
        "visualChannel": "system",
        "accentKey": "system",
        "glyphSource": _glyph_for_kind("issue", "system"),
        "updatedAt": _now_iso(),
        "updatedLabel": "刚刚",
        "relativeLabel": "刚刚",
        "isLive": is_live,
        "personaVariant": "automation",
        "avatarSource": avatar_source,
        "routeKind": "profile",
        "routeValue": profile_id,
        "canOpen": True,
        "canToggleCron": False,
        "canRunHeartbeat": False,
    }


def _build_startup_activity_unit(
    *,
    profile_id: str,
    avatar_source: str,
    startup_activity: dict[str, Any],
    is_live: bool,
) -> dict[str, Any] | None:
    if str(startup_activity.get("kind", "") or "") != "startup_greeting":
        return None
    status = str(startup_activity.get("status", "") or "").strip()
    if status not in {"running", "completed", "error"}:
        return None
    channel_keys = _dedupe_channel_keys(startup_activity.get("channelKeys", []) or [])
    primary_channel = _primary_visual_channel(channel_keys)
    if primary_channel in channel_keys:
        channel_keys = [primary_channel] + [key for key in channel_keys if key != primary_channel]
    session_keys = [
        str(value).strip()
        for value in startup_activity.get("sessionKeys", [])
        if str(value).strip()
    ]
    session_key = str(startup_activity.get("sessionKey", "") or "").strip()
    if session_key and session_key not in session_keys:
        session_keys.append(session_key)
    primary_session_key = session_keys[0] if len(session_keys) == 1 else ""
    error_text = _safe_text(startup_activity.get("error", "") or "", limit=44)
    summary = {
        "running": "启动后正在发送问候",
        "completed": "刚发送完问候",
        "error": error_text or "问候发送失败",
    }.get(status, "")
    return {
        "id": f"{profile_id}:startup:greeting",
        "profileId": profile_id,
        "kind": "startup_greeting",
        "title": "AI 问候",
        "summary": summary,
        "sessionKey": primary_session_key,
        "sessionKeys": session_keys,
        "channelKeys": channel_keys,
        "visualChannel": primary_channel,
        "accentKey": primary_channel,
        "glyphSource": _glyph_for_kind("session_reply", primary_channel),
        "statusKey": "running" if status == "running" else ("completed" if status == "completed" else "error"),
        "statusLabel": {
            "running": "发送中",
            "completed": "已完成",
            "error": "待处理",
        }[status],
        "updatedAt": str(startup_activity.get("updatedAt", "") or ""),
        "updatedLabel": _relative_time(startup_activity.get("updatedAt")),
        "relativeLabel": _relative_time(startup_activity.get("updatedAt")),
        "isLive": is_live,
        "personaVariant": "primary",
        "avatarSource": avatar_source,
        "routeKind": "session" if primary_session_key else "profile",
        "routeValue": primary_session_key or profile_id,
        "canOpen": bool(primary_session_key or profile_id),
        "canToggleCron": False,
        "canRunHeartbeat": False,
        "isRunning": status == "running",
    }


class ProfileWorkSupervisorService(QObject):
    overviewChanged = Signal()
    profilesChanged = Signal()
    workingChanged = Signal()
    completedChanged = Signal()
    automationChanged = Signal()
    attentionChanged = Signal()
    selectionChanged = Signal()
    busyChanged = Signal(bool)
    profileNavigationRequested = Signal(str)

    _refreshResult = Signal(object)

    def __init__(
        self,
        runner: AsyncioRunner,
        *,
        profile_service: Any,
        session_service: Any,
        chat_service: Any,
        cron_service: Any,
        heartbeat_service: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._profile_service = profile_service
        self._session_service = session_service
        self._chat_service = chat_service
        self._cron_service = cron_service
        self._heartbeat_service = heartbeat_service
        self._overview: dict[str, Any] = {}
        self._profiles: list[dict[str, Any]] = []
        self._all_items = self._empty_collections()
        self._visible_items = self._empty_collections()
        self._selected_profile_id = ""
        self._selected_item_id = ""
        self._busy = False
        self._pending_action: dict[str, Any] | None = None
        self._refreshResult.connect(self._handle_refresh_result)
        self._wire_signals()

    def _empty_collections(self) -> dict[str, list[dict[str, Any]]]:
        return {name: [] for name in _COLLECTION_NAMES}

    def _section_items(self, section: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._visible_items.get(section, [])]

    def _wire_signals(self) -> None:
        _ = self._profile_service.activeProfileChanged.connect(self._on_profile_switched)
        _ = self._profile_service.profilesChanged.connect(self.refresh)
        _ = self._session_service.sessionsChanged.connect(self.refresh)
        _ = self._session_service.sessionManagerReady.connect(self._on_session_manager_ready)
        _ = self._chat_service.stateChanged.connect(lambda _state: self.refresh())
        _ = self._chat_service.errorChanged.connect(lambda _error: self.refresh())
        _ = self._chat_service.gatewayChannelsChanged.connect(self.refresh)
        _ = self._chat_service.gatewayDetailChanged.connect(self.refresh)
        _ = self._chat_service.startupActivityChanged.connect(self.refresh)
        _ = self._cron_service.tasksChanged.connect(self.refresh)
        _ = self._cron_service.profileChanged.connect(self.refresh)
        _ = self._heartbeat_service.stateChanged.connect(self.refresh)
        _ = self._heartbeat_service.profileChanged.connect(self.refresh)

    @Property(dict, notify=overviewChanged)
    def overview(self) -> dict[str, Any]:
        return dict(self._overview)

    @Property(list, notify=profilesChanged)
    def profiles(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._profiles]

    @Property(list, notify=workingChanged)
    def workingItems(self) -> list[dict[str, Any]]:
        return self._section_items("working")

    @Property(list, notify=completedChanged)
    def completedItems(self) -> list[dict[str, Any]]:
        return self._section_items("completed")

    @Property(list, notify=automationChanged)
    def automationItems(self) -> list[dict[str, Any]]:
        return self._section_items("automation")

    @Property(list, notify=attentionChanged)
    def attentionItems(self) -> list[dict[str, Any]]:
        return self._section_items("attention")

    @Property(dict, notify=selectionChanged)
    def selectedProfile(self) -> dict[str, Any]:
        for item in self._profiles:
            if str(item.get("id", "")) == self._selected_profile_id:
                return dict(item)
        return {}

    @Property(dict, notify=selectionChanged)
    def selectedItem(self) -> dict[str, Any]:
        if not self._selected_item_id:
            return {}
        for collection in self._visible_items.values():
            for item in collection:
                if str(item.get("id", "")) == self._selected_item_id:
                    return dict(item)
        return {}

    @Property(bool, notify=selectionChanged)
    def hasSelection(self) -> bool:
        return bool(self._selected_profile_id or self._selected_item_id)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Slot()
    def refresh(self) -> None:
        self._set_busy(True)
        snapshot = self._capture_active_inputs()
        future = self._submit_safe(self._build_projection(snapshot))
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_refresh_done)

    @Slot(str)
    def selectProfile(self, profile_id: str) -> None:
        self._set_profile_filter(str(profile_id or "").strip(), toggle=True)

    @Slot()
    def clearProfileFilter(self) -> None:
        self._set_profile_filter("", toggle=False)

    @Slot(str)
    def selectItem(self, item_id: str) -> None:
        self._selected_item_id = str(item_id or "").strip()
        self.selectionChanged.emit()

    @Slot()
    def clearSelection(self) -> None:
        if not self._selected_item_id:
            return
        self._selected_item_id = ""
        self.selectionChanged.emit()

    @Slot(str)
    def activateProfile(self, profile_id: str) -> None:
        next_id = str(profile_id or "").strip()
        if not next_id:
            return
        self._profile_service.activateProfile(next_id)

    @Slot()
    def openSelectedTarget(self) -> None:
        selected = self.selectedItem
        if not selected:
            selected_profile = self.selectedProfile
            if selected_profile:
                self.activateProfile(str(selected_profile.get("id", "")))
            return
        profile_id = str(selected.get("profileId", "") or "")
        route_kind = str(selected.get("routeKind", "") or "")
        route_value = str(selected.get("routeValue", "") or "")
        self._queue_or_run_action(
            profile_id,
            action={"kind": route_kind, "value": route_value},
        )

    @Slot()
    def toggleSelectedCron(self) -> None:
        selected = self.selectedItem
        if not selected or str(selected.get("kind", "")) != "cron_job":
            return
        profile_id = str(selected.get("profileId", "") or "")
        self._queue_or_run_action(
            profile_id,
            action={"kind": "toggle_cron", "value": str(selected.get("routeValue", "") or "")},
        )

    @Slot()
    def runSelectedHeartbeat(self) -> None:
        selected = self.selectedItem
        if not selected or str(selected.get("kind", "")) != "heartbeat_check":
            return
        profile_id = str(selected.get("profileId", "") or "")
        self._queue_or_run_action(profile_id, action={"kind": "heartbeat", "value": "heartbeat"})

    @Slot()
    def toggleActiveGateway(self) -> None:
        state = str(getattr(self._chat_service, "state", "") or "")
        if state in {"running", "starting"}:
            self._chat_service.stop()
        else:
            self._chat_service.start()

    def _queue_or_run_action(self, profile_id: str, *, action: dict[str, Any]) -> None:
        active_profile_id = str(getattr(self._profile_service, "activeProfileId", "") or "")
        next_profile_id = str(profile_id or "").strip()
        if next_profile_id and next_profile_id != active_profile_id:
            self._pending_action = {"profile_id": next_profile_id, **action}
            self._profile_service.activateProfile(next_profile_id)
            return
        self._run_pending_action(action)

    def _on_profile_switched(self) -> None:
        self.refresh()
        self._try_flush_pending_action(session_manager_ready=False)

    def _on_session_manager_ready(self, _manager: object) -> None:
        self.refresh()
        self._try_flush_pending_action(session_manager_ready=True)

    def _pending_action_needs_session_manager(self, action: dict[str, Any]) -> bool:
        return str(action.get("kind", "") or "") == "session"

    def _try_flush_pending_action(self, *, session_manager_ready: bool) -> None:
        action = self._pending_action
        if action is None:
            return
        expected_profile = str(action.get("profile_id", "") or "")
        active_profile_id = str(getattr(self._profile_service, "activeProfileId", "") or "")
        if not expected_profile or expected_profile != active_profile_id:
            return
        if self._pending_action_needs_session_manager(action) and not session_manager_ready:
            return
        self._pending_action = None
        self._run_pending_action(dict(action))

    def _open_cron_target(self, task_id: str, *, toggle_enabled: bool) -> None:
        self.profileNavigationRequested.emit("cron")
        self._cron_service.selectTask(task_id)
        if not toggle_enabled:
            return
        selected_task = getattr(self._cron_service, "selectedTask", {})
        if isinstance(selected_task, dict):
            enabled = bool(selected_task.get("enabled", False))
            self._cron_service.toggleEnabled(not enabled)

    def _run_pending_action(self, action: dict[str, Any]) -> None:
        kind = str(action.get("kind", "") or "")
        value = str(action.get("value", "") or "")
        if kind == "profile" and value:
            self._set_profile_filter(value, toggle=False)
            return
        if kind == "session" and value:
            self.profileNavigationRequested.emit("sessions")
            self._session_service.selectSession(value)
            return
        if kind == "cron" and value:
            self._open_cron_target(value, toggle_enabled=False)
            return
        if kind == "toggle_cron" and value:
            self._open_cron_target(value, toggle_enabled=True)
            return
        if kind == "heartbeat":
            self.profileNavigationRequested.emit("cron")
            self._heartbeat_service.runNow()
            return

    def _set_profile_filter(self, profile_id: str, *, toggle: bool) -> None:
        next_id = str(profile_id or "").strip()
        if toggle and self._selected_profile_id == next_id:
            next_id = ""
        if self._selected_profile_id == next_id and not self._selected_item_id:
            return
        self._selected_profile_id = next_id
        self._selected_item_id = ""
        self.selectionChanged.emit()
        self._apply_filter()
        self._emit_collection_changes()

    def _session_snapshot(self) -> list[dict[str, Any]]:
        snapshot_fn = getattr(self._session_service, "supervisorSessionsSnapshot", None)
        if callable(snapshot_fn):
            return _clone_dict_list(snapshot_fn())
        return _clone_dict_list(getattr(getattr(self._session_service, "_model", None), "_sessions", []))

    def _cron_snapshot(self) -> list[dict[str, Any]]:
        snapshot_fn = getattr(self._cron_service, "supervisorTasksSnapshot", None)
        if callable(snapshot_fn):
            return _clone_dict_list(snapshot_fn())
        return _clone_dict_list(getattr(self._cron_service, "_all_tasks", []))

    def _heartbeat_snapshot(self) -> dict[str, Any]:
        snapshot_fn = getattr(self._heartbeat_service, "supervisorSnapshot", None)
        if callable(snapshot_fn):
            snapshot = snapshot_fn()
            if isinstance(snapshot, dict):
                next_snapshot = dict(snapshot)
                next_snapshot.setdefault("updated_at", _now_iso())
                return next_snapshot
        heartbeat_status = {
            "enabled": bool(getattr(self._heartbeat_service, "enabled", False)),
            "heartbeat_file": str(getattr(self._heartbeat_service, "heartbeatFilePath", "") or ""),
            "heartbeat_file_exists": bool(
                getattr(self._heartbeat_service, "heartbeatFileExists", False)
            ),
            "last_checked_at_ms": getattr(self._heartbeat_service, "_snapshot", {}).get(
                "last_checked_at_ms"
            ),
            "last_run_at_ms": getattr(self._heartbeat_service, "_snapshot", {}).get("last_run_at_ms"),
            "last_decision": str(getattr(self._heartbeat_service, "lastDecisionLabel", "") or ""),
            "last_error": str(getattr(self._heartbeat_service, "lastError", "") or ""),
            "updated_at": _now_iso(),
        }
        effective_live = getattr(self._heartbeat_service, "_effective_live", None)
        live_heartbeat = effective_live() if callable(effective_live) else None
        live_status = live_heartbeat.status() if live_heartbeat is not None else {}
        heartbeat_status["running"] = bool(live_status.get("running", False))
        return heartbeat_status

    def _gateway_snapshot(self) -> dict[str, Any]:
        snapshot_fn = getattr(self._chat_service, "supervisorGatewaySnapshot", None)
        if callable(snapshot_fn):
            snapshot = snapshot_fn()
            if isinstance(snapshot, dict):
                return dict(snapshot)
        return {
            "state": str(getattr(self._chat_service, "gatewayState", "") or ""),
            "detail": str(getattr(self._chat_service, "gatewayDetail", "") or ""),
            "error": str(getattr(self._chat_service, "lastError", "") or ""),
            "detail_is_error": bool(getattr(self._chat_service, "gatewayDetailIsError", False)),
            "channels": list(getattr(self._chat_service, "gatewayChannels", []) or []),
            "startup_activity": dict(getattr(self._chat_service, "startupActivity", {}) or {}),
        }

    def _capture_active_inputs(self) -> dict[str, Any]:
        active_context = profile_context_from_mapping(
            getattr(self._profile_service, "activeProfileContext", None)
        )
        gateway_snapshot = self._gateway_snapshot()
        return {
            "shared_workspace_path": str(getattr(self._profile_service, "sharedWorkspacePath", "") or ""),
            "active_profile_id": str(getattr(self._profile_service, "activeProfileId", "") or ""),
            "active_context": active_context,
            "active_sessions": self._session_snapshot(),
            "active_cron_items": self._cron_snapshot(),
            "heartbeat_status": self._heartbeat_snapshot(),
            "gateway_state": str(gateway_snapshot.get("state", "") or ""),
            "gateway_detail": str(gateway_snapshot.get("detail", "") or ""),
            "gateway_error": str(gateway_snapshot.get("error", "") or ""),
            "gateway_detail_is_error": bool(gateway_snapshot.get("detail_is_error", False)),
            "gateway_channels": list(gateway_snapshot.get("channels", []) or []),
            "startup_activity": dict(gateway_snapshot.get("startup_activity", {}) or {}),
        }

    def _submit_safe(self, coro: Any) -> Any:
        try:
            return self._runner.submit(coro)
        except RuntimeError:
            coro.close()
            return None

    async def _build_projection(self, captured: dict[str, Any]) -> dict[str, Any]:
        return await self._runner.run_bg_io(self._build_projection_sync, captured)

    def _build_projection_sync(self, captured: dict[str, Any]) -> dict[str, Any]:
        shared_workspace_path = str(captured.get("shared_workspace_path", "") or "")
        if not shared_workspace_path:
            return _empty_projection()
        shared_workspace = Path(shared_workspace_path).expanduser()
        registry = ensure_profile_registry(shared_workspace)
        active_context = captured.get("active_context")
        active_profile_id = str(captured.get("active_profile_id", "") or "")
        profile_cards: list[dict[str, Any]] = []
        working_items: list[dict[str, Any]] = []
        completed_items: list[dict[str, Any]] = []
        automation_items: list[dict[str, Any]] = []
        attention_items: list[dict[str, Any]] = []
        for spec in registry.profiles:
            context = profile_context(spec.id, shared_workspace=shared_workspace, registry=registry)
            if active_context is not None and spec.id == active_profile_id:
                payload = self._build_live_profile_payload(
                    spec=spec,
                    sessions=_clone_dict_list(captured.get("active_sessions", [])),
                    cron_items=_clone_dict_list(captured.get("active_cron_items", [])),
                    heartbeat_status=dict(captured.get("heartbeat_status", {})),
                    gateway_state=str(captured.get("gateway_state", "") or ""),
                    gateway_detail=str(captured.get("gateway_detail", "") or ""),
                    gateway_error=str(captured.get("gateway_error", "") or ""),
                    gateway_detail_is_error=bool(captured.get("gateway_detail_is_error", False)),
                    gateway_channels=list(captured.get("gateway_channels", []) or []),
                    startup_activity=dict(captured.get("startup_activity", {}) or {}),
                )
                _write_snapshot(_snapshot_path(context), payload["snapshot"])
            else:
                payload = self._build_cached_profile_payload(spec=spec, context=context)
            profile_cards.append(payload["profile"])
            working_items.extend(payload["working"])
            completed_items.extend(payload["completed"])
            automation_items.extend(payload["automation"])
            attention_items.extend(payload["attention"])
        working_items.sort(
            key=lambda item: (
                bool(item.get("isRunning", False)),
                str(item.get("updatedAt", "") or ""),
            ),
            reverse=True,
        )
        completed_items = _filter_recent_completed_items(completed_items)
        automation_items.sort(key=lambda item: str(item.get("updatedAt", "") or ""), reverse=True)
        attention_items.sort(key=lambda item: str(item.get("updatedAt", "") or ""), reverse=True)
        overview = {
            "title": "指挥舱",
            "subtitle": "统一查看分身回复、自动化与待处理事项",
            "profileCount": len(profile_cards),
            "workingCount": len(working_items),
            "completedCount": len(completed_items),
            "automationCount": len(automation_items),
            "attentionCount": len(attention_items),
            "liveProfileId": active_profile_id,
            "liveProfileName": str(
                next((item.get("displayName", "") for item in profile_cards if item.get("id") == active_profile_id), "")
            ),
            "updatedAt": _now_iso(),
            "updatedLabel": _relative_time(_now_iso()),
        }
        return {
            "overview": overview,
            "profiles": profile_cards,
            "working": working_items,
            "completed": completed_items,
            "automation": automation_items,
            "attention": attention_items,
        }

    def _build_live_profile_payload(
        self,
        *,
        spec: ProfileSpec,
        sessions: list[dict[str, Any]],
        cron_items: list[dict[str, Any]],
        heartbeat_status: dict[str, Any],
        gateway_state: str,
        gateway_detail: str,
        gateway_error: str,
        gateway_detail_is_error: bool,
        gateway_channels: list[object],
        startup_activity: dict[str, Any],
    ) -> dict[str, Any]:
        avatar_source = _avatar_source(spec.avatar_key)
        gateway_live = _is_gateway_live(gateway_state)
        inventory = _session_inventory(sessions, gateway_channels=gateway_channels)
        session_units, session_workers = _build_session_work_units(
            profile_id=spec.id,
            avatar_source=avatar_source,
            sessions=sessions,
            is_live=True,
        )
        cron_units, cron_workers, cron_issues = _build_cron_work_units(
            profile_id=spec.id,
            avatar_source=avatar_source,
            cron_items=cron_items,
            is_live=True,
        )
        heartbeat_unit, heartbeat_issue = _build_heartbeat_work_unit(
            profile_id=spec.id,
            avatar_source=avatar_source,
            heartbeat_status=heartbeat_status,
            is_live=True,
        )
        startup_unit = _build_startup_activity_unit(
            profile_id=spec.id,
            avatar_source=avatar_source,
            startup_activity=startup_activity,
            is_live=True,
        )
        gateway_issue = _build_gateway_issue(
            profile_id=spec.id,
            avatar_source=avatar_source,
            gateway_state=gateway_state,
            gateway_detail=gateway_detail,
            gateway_error=gateway_error,
            gateway_detail_is_error=gateway_detail_is_error,
            is_live=True,
        )
        working = (
            [unit for unit in session_units if bool(unit.get("isRunning", False))]
            if gateway_live
            else []
        )
        completed = [
            unit
            for unit in session_units
            if str(unit.get("kind", "") or "") == "subagent_task"
            and str(unit.get("statusKey", "") or "") == "completed"
        ]
        if startup_unit is not None:
            if str(startup_unit.get("statusKey", "") or "") == "running":
                working.insert(0, startup_unit)
            elif str(startup_unit.get("statusKey", "") or "") == "completed":
                completed.insert(0, startup_unit)
        automation = cron_units + ([heartbeat_unit] if heartbeat_unit else [])
        attention = cron_issues + ([heartbeat_issue] if heartbeat_issue else [])
        if startup_unit is not None and str(startup_unit.get("statusKey", "") or "") == "error":
            attention.insert(0, startup_unit)
        if gateway_issue is not None:
            attention.append(gateway_issue)
        workers = (session_workers + cron_workers)[:8]
        if heartbeat_unit is not None:
            workers.append(
                _build_worker_token(
                    profile_id=spec.id,
                    avatar_source=avatar_source,
                    title="自动检查",
                    variant="automation",
                    accent_key="heartbeat",
                    glyph_source=_glyph_for_kind("heartbeat_check", "heartbeat"),
                    status_key=str(heartbeat_unit.get("statusKey", "idle")),
                    status_label=str(heartbeat_unit.get("statusLabel", "待命")),
                    route_kind="heartbeat",
                    route_value="heartbeat",
                    unit_id=f"{spec.id}:heartbeat",
                )
            )
        running_count = len(working)
        session_metrics = _session_metrics(working)
        automation_metrics = _automation_metrics(automation)
        updated_at = _now_iso()
        snapshot = {
            "schema_version": _SNAPSHOT_SCHEMA_VERSION,
            "profile_id": spec.id,
            "display_name": spec.display_name,
            "avatar_key": spec.avatar_key,
            "updated_at": updated_at,
            "gateway": {
                "state": gateway_state,
                "detail": gateway_detail,
                "channels": _gateway_channel_keys(gateway_channels),
                "is_live": gateway_live,
            },
            "counts": {
                "running": running_count,
                "completed": len(completed),
                "automation": len(automation),
                "attention": len(attention),
            },
            "inventory": dict(inventory),
            "workers": workers,
            "working": working,
            "completed": completed,
            "automation": automation,
            "attention": attention,
        }
        profile_card = _build_profile_card(
            spec=spec,
            avatar_source=avatar_source,
            is_active=True,
            updated_at=updated_at,
            live_label="实时" if gateway_live else "当前",
            snapshot_label="实时更新" if gateway_live else "网关未启动",
            status_summary=_profile_status_summary(
                is_active=True,
                is_live=gateway_live,
                session_reply_count=int(session_metrics["sessionReplyCount"]),
                subagent_count=int(session_metrics["subagentCount"]),
                other_working_count=max(
                    0,
                    running_count
                    - int(session_metrics["sessionReplyCount"])
                    - int(session_metrics["subagentCount"]),
                ),
                automation_count=len(automation),
                total_session_count=int(inventory["totalSessionCount"]),
                total_child_session_count=int(inventory["totalChildSessionCount"]),
            ),
            working_count=running_count,
            automation_count=len(automation),
            attention_count=len(attention),
            inventory=inventory,
            session_reply_count=int(session_metrics["sessionReplyCount"]),
            subagent_count=int(session_metrics["subagentCount"]),
            running_automation_count=int(automation_metrics["runningAutomationCount"]),
            gateway_state=gateway_state,
            gateway_detail=gateway_detail,
            is_gateway_live=gateway_live,
            workers=workers,
        )
        return {
            "profile": profile_card,
            "working": working,
            "completed": completed,
            "automation": automation,
            "attention": attention,
            "snapshot": snapshot,
        }

    def _load_cached_profile_state(
        self,
        *,
        spec: ProfileSpec,
        context: ProfileContext,
        avatar_source: str,
    ) -> dict[str, Any]:
        snapshot_path = _snapshot_path(context)
        snapshot, snapshot_changed = _normalize_snapshot_payload(
            _read_snapshot(snapshot_path),
            profile_id=spec.id,
        )
        if snapshot_changed:
            _write_snapshot(snapshot_path, snapshot)
        working: list[dict[str, Any]] = []
        completed = _clone_dict_list(snapshot.get("completed", []))
        automation = _clone_dict_list(snapshot.get("automation", []))
        attention = _clone_dict_list(snapshot.get("attention", []))
        workers = _clone_dict_list(snapshot.get("workers", []))
        gateway = dict(snapshot.get("gateway", {}) or {})
        gateway_channels = list(gateway.get("channels", []) or [])
        if not working and not completed and not automation and not attention and not workers:
            try:
                cron_items = _load_cron_items(context.cron_store_path)
            except Exception:
                cron_items = []
            cron_units, cron_workers, cron_issues = _build_cron_work_units(
                profile_id=spec.id,
                avatar_source=avatar_source,
                cron_items=cron_items,
                is_live=False,
            )
            automation = cron_units
            attention = cron_issues
            workers = cron_workers[:4]
            heartbeat_unit, heartbeat_issue = _build_heartbeat_work_unit(
                profile_id=spec.id,
                avatar_source=avatar_source,
                heartbeat_status=_heartbeat_static_snapshot(context.heartbeat_file),
                is_live=False,
            )
            if heartbeat_unit is not None:
                automation.append(heartbeat_unit)
            if heartbeat_issue is not None:
                attention.append(heartbeat_issue)
        snapshot_inventory = dict(snapshot.get("inventory", {}) or {})
        inventory = {
            "totalSessionCount": int(snapshot_inventory.get("totalSessionCount", 0) or 0),
            "totalChildSessionCount": int(snapshot_inventory.get("totalChildSessionCount", 0) or 0),
            "channelKeys": _dedupe_channel_keys(snapshot_inventory.get("channelKeys", []) or []),
        }
        if (
            not inventory["totalSessionCount"]
            and not inventory["totalChildSessionCount"]
            and not inventory["channelKeys"]
        ):
            try:
                stored_sessions = _load_sessions_from_root(context.state_root)
            except Exception:
                stored_sessions = []
            inventory = _session_inventory(stored_sessions, gateway_channels=gateway_channels)
        return {
            "snapshot_updated_at": str(snapshot.get("updated_at", "") or ""),
            "working": working,
            "completed": completed,
            "automation": automation,
            "attention": attention,
            "workers": workers,
            "inventory": inventory,
            "gateway_state": str(gateway.get("state", "") or ""),
            "gateway_detail": str(gateway.get("detail", "") or ""),
            "is_gateway_live": bool(gateway.get("is_live", False)),
        }

    def _build_cached_profile_payload(
        self,
        *,
        spec: ProfileSpec,
        context: ProfileContext,
    ) -> dict[str, Any]:
        avatar_source = _avatar_source(spec.avatar_key)
        cached_state = self._load_cached_profile_state(
            spec=spec,
            context=context,
            avatar_source=avatar_source,
        )
        working = list(cached_state["working"])
        completed = list(cached_state["completed"])
        automation = list(cached_state["automation"])
        attention = list(cached_state["attention"])
        workers = list(cached_state["workers"])
        inventory = dict(cached_state["inventory"])
        automation_metrics = _automation_metrics(automation)
        profile_card = _build_profile_card(
            spec=spec,
            avatar_source=avatar_source,
            is_active=False,
            updated_at=str(cached_state["snapshot_updated_at"]),
            live_label="",
            snapshot_label="",
            status_summary=_profile_status_summary(
                is_active=False,
                is_live=False,
                session_reply_count=0,
                subagent_count=0,
                other_working_count=0,
                automation_count=len(automation),
                total_session_count=int(inventory["totalSessionCount"]),
                total_child_session_count=int(inventory["totalChildSessionCount"]),
            ),
            working_count=len(working),
            automation_count=len(automation),
            attention_count=len(attention),
            inventory=inventory,
            session_reply_count=0,
            subagent_count=0,
            running_automation_count=int(automation_metrics["runningAutomationCount"]),
            gateway_state=str(cached_state["gateway_state"]),
            gateway_detail=str(cached_state["gateway_detail"]),
            is_gateway_live=bool(cached_state["is_gateway_live"]),
            workers=workers,
        )
        return {
            "profile": profile_card,
            "working": working,
            "completed": completed,
            "automation": automation,
            "attention": attention,
        }

    def _on_refresh_done(self, future: Any) -> None:
        if future.cancelled():
            self._set_busy(False)
            return
        exc = future.exception()
        if exc:
            self._refreshResult.emit(
                {
                    "overview": self._overview,
                    "profiles": self._profiles,
                    **{name: self._all_items.get(name, []) for name in _COLLECTION_NAMES},
                }
            )
            self._set_busy(False)
            return
        self._refreshResult.emit(future.result())

    def _handle_refresh_result(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self._overview = dict(data.get("overview", {}) if isinstance(data, dict) else {})
        self._profiles = [dict(item) for item in data.get("profiles", []) if isinstance(item, dict)]
        valid_profile_ids = {str(item.get("id", "")) for item in self._profiles}
        selection_changed = False
        if self._selected_profile_id and self._selected_profile_id not in valid_profile_ids:
            self._selected_profile_id = ""
            self._selected_item_id = ""
            selection_changed = True
        self._all_items = {
            name: _clone_dict_list(data.get(name, []))
            for name in _COLLECTION_NAMES
        }
        self._apply_filter()
        self._set_busy(False)
        if selection_changed:
            self.selectionChanged.emit()
        self.overviewChanged.emit()
        self.profilesChanged.emit()
        self._emit_collection_changes()

    def _apply_filter(self) -> None:
        profile_id = self._selected_profile_id
        if not profile_id:
            self._visible_items = {
                name: [dict(item) for item in items]
                for name, items in self._all_items.items()
            }
        else:
            self._visible_items = {
                name: [
                    dict(item)
                    for item in items
                    if str(item.get("profileId", "")) == profile_id
                ]
                for name, items in self._all_items.items()
            }
        if self._selected_item_id:
            item = self.selectedItem
            if not item:
                self._selected_item_id = ""
                self.selectionChanged.emit()

    def _emit_collection_changes(self) -> None:
        self.workingChanged.emit()
        self.completedChanged.emit()
        self.automationChanged.emit()
        self.attentionChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busyChanged.emit(busy)
