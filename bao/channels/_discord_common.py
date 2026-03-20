"""Shared Discord helpers."""

from __future__ import annotations

import json

DISCORD_API_BASE = "https://discord.com/api/v10"
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_MESSAGE_LEN = 2000


def _split_message(content: str, max_len: int = MAX_MESSAGE_LEN) -> list[str]:
    if not content:
        return []
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos <= 0:
            pos = cut.rfind(" ")
        if pos <= 0:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False)
