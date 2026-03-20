from __future__ import annotations

import json
from typing import Any


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    s = text.strip()
    rows: list[dict[str, Any]] = []
    if not s:
        return rows

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return [obj]
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        pass

    for line in text.splitlines():
        t = line.strip()
        if not t:
            continue
        try:
            obj = json.loads(t)
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


def extract_session_id(obj: dict[str, Any]) -> str | None:
    direct = obj.get("session_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    camel = obj.get("sessionId")
    if isinstance(camel, str) and camel.strip():
        return camel.strip()
    return None


def extract_text_fallback(rows: list[dict[str, Any]]) -> str | None:
    candidates: list[str] = []
    for obj in rows:
        hit = find_first_string_by_keys(
            obj,
            (
                "message",
                "content",
                "text",
                "output",
                "response",
                "final_message",
                "finalMessage",
            ),
        )
        if hit:
            candidates.append(hit)
    return candidates[-1] if candidates else None


def extract_contract_fields(text: str) -> tuple[str | None, str | None]:
    rows = extract_json_objects(text)
    if not rows:
        return None, None

    primary = rows[-1]
    session_id = extract_session_id(primary)
    if not session_id:
        for obj in reversed(rows[:-1]):
            session_id = extract_session_id(obj)
            if session_id:
                break

    result = primary.get("result") if isinstance(primary, dict) else None
    if isinstance(result, str) and result.strip():
        return result.strip(), session_id
    for obj in reversed(rows[:-1]):
        candidate = obj.get("result") if isinstance(obj, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip(), session_id

    return extract_text_fallback(rows), session_id
