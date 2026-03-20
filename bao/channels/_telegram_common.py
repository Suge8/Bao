"""Shared Telegram channel helpers."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import Any, TypeVar

from loguru import logger
from telegram.error import BadRequest, NetworkError, TelegramError

_T = TypeVar("_T")
_UPDATER_CLEANUP_LOG = (
    "Error while calling `get_updates` one more time to mark all fetched updates."
)


def _markdown_to_telegram_html(text: str) -> str:
    if not text:
        return ""

    code_blocks: list[str] = []

    def save_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    for index, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{index}\x00", f"<code>{escaped}</code>")

    for index, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{index}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def _is_telegram_parse_error(error: BadRequest) -> bool:
    message = str(error).lower()
    return "parse" in message or "entity" in message or "tag" in message


def _is_message_not_modified(error: BadRequest) -> bool:
    return "message is not modified" in str(error).lower()


def _split_message(content: str, max_len: int = 4000) -> list[str]:
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos == -1:
            pos = cut.rfind(" ")
        if pos == -1:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


def _on_polling_error(exc: TelegramError, channel_logger=logger) -> None:
    if isinstance(exc, NetworkError):
        channel_logger.warning("⚠️ Telegram polling 网络波动 / polling network issue: {}", exc)
        return
    channel_logger.error("❌ Telegram polling 异常 / polling error: {}", exc)


async def _run_start_step(label: str, operation: Callable[[], Awaitable[_T]]) -> _T:
    try:
        return await operation()
    except Exception as exc:
        raise RuntimeError(f"{label}: {exc.__class__.__name__}: {exc}") from exc


@contextmanager
def _suppress_updater_cleanup_log() -> Any:
    updater_logger = logging.getLogger("telegram.ext.Updater")

    class _CleanupFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return _UPDATER_CLEANUP_LOG not in record.getMessage()

    cleanup_filter = _CleanupFilter()
    updater_logger.addFilter(cleanup_filter)
    try:
        yield
    finally:
        updater_logger.removeFilter(cleanup_filter)
