from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_last_output_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        return ""
    try:
        return file_path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        elif isinstance(obj, list):
            rows.extend(x for x in obj if isinstance(x, dict))
    return rows


def find_first_string_by_keys(obj: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(obj, dict):
        for key in keys:
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for val in obj.values():
            hit = find_first_string_by_keys(val, keys)
            if hit:
                return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = find_first_string_by_keys(item, keys)
            if hit:
                return hit
    return None


def extract_session_id_from_jsonl(text: str) -> str | None:
    rows = extract_json_objects(text)
    for obj in rows:
        if obj.get("type") == "thread.started":
            tid = obj.get("thread_id") or obj.get("threadId")
            if isinstance(tid, str) and tid.strip():
                return tid.strip()
    for obj in rows:
        sid = find_first_string_by_keys(
            obj,
            (
                "thread_id",
                "threadId",
                "session_id",
                "sessionId",
                "conversation_id",
                "conversationId",
            ),
        )
        if sid:
            return sid
    return None


def extract_last_message_from_jsonl(text: str) -> str | None:
    rows = extract_json_objects(text)
    candidates: list[str] = []
    for obj in rows:
        msg = find_first_string_by_keys(
            obj,
            (
                "final_message",
                "finalMessage",
                "last_message",
                "lastMessage",
                "message",
                "content",
                "text",
            ),
        )
        if msg:
            candidates.append(msg)
    return candidates[-1] if candidates else None
