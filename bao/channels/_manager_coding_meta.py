from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bao.bus.events import OutboundMessage

_STATUS_ICONS = {"success": "✅", "error": "❌", "timeout": "⏱️"}


@dataclass(frozen=True)
class CodingMetaRule:
    provider: str
    marker: str
    meta_key: str
    status_key: str

    @property
    def completion_line(self) -> str:
        return f"{self.provider} completed successfully."


_CODING_META_RULES = (
    CodingMetaRule("OpenCode", "OPENCODE_META=", "_opencode_meta", "_opencode_status"),
    CodingMetaRule("Codex", "CODEX_META=", "_codex_meta", "_codex_status"),
    CodingMetaRule("Claude Code", "CLAUDECODE_META=", "_claudecode_meta", "_claudecode_status"),
)


def transform_coding_meta(msg: OutboundMessage) -> OutboundMessage:
    if msg.metadata.get("_progress") or not msg.content:
        return msg
    for rule in _CODING_META_RULES:
        meta, cleaned = _parse_meta_line(msg.content, rule.marker)
        if not meta:
            continue
        final_content = _merge_status_and_content(rule, meta, cleaned)
        new_meta = dict(msg.metadata)
        new_meta[rule.meta_key] = meta
        new_meta[rule.status_key] = str(meta.get("status") or "unknown")
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            reply_to=msg.reply_to,
            media=msg.media,
            metadata=new_meta,
        )
    return msg


def _parse_meta_line(content: str, marker: str) -> tuple[dict[str, Any] | None, str]:
    if marker not in content:
        return None, content
    meta: dict[str, Any] | None = None
    kept: list[str] = []
    for line in content.splitlines():
        if line.startswith(marker) and meta is None:
            raw = line.split("=", 1)[1].strip()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                meta = parsed
                continue
        kept.append(line)
    return meta, "\n".join(kept).rstrip("\n")


def _merge_status_and_content(rule: CodingMetaRule, meta: dict[str, Any], cleaned: str) -> str:
    lines = cleaned.splitlines()
    if lines and lines[0].strip().lower() == rule.completion_line.lower():
        cleaned = "\n".join(lines[1:]).lstrip("\n")
    status_line = _render_status(rule.provider, meta)
    if not cleaned:
        return status_line
    return f"{status_line}\n\n{cleaned}"


def _render_status(provider: str, meta: dict[str, Any]) -> str:
    status = str(meta.get("status") or "unknown")
    parts = [f"{_STATUS_ICONS.get(status, '⌨️')} {provider} status: {status}"]
    attempts = meta.get("attempts")
    duration_ms = meta.get("duration_ms")
    session_id = meta.get("session_id")
    error_type = meta.get("error_type")
    if isinstance(attempts, int):
        parts.append(f"attempts={attempts}")
    if isinstance(duration_ms, int):
        parts.append(f"duration={duration_ms / 1000:.1f}s")
    if isinstance(session_id, str) and session_id:
        parts.append(f"session={session_id}")
    if isinstance(error_type, str) and error_type:
        parts.append(f"error={error_type}")
    return " | ".join(parts)
