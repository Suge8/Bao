from __future__ import annotations

import inspect
import platform
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ._context_types import LazyMemoryStoreOptions


def format_current_time(*, include_weekday: bool = True) -> str:
    fmt = "%Y-%m-%d %H:%M (%A)" if include_weekday else "%Y-%m-%d %H:%M"
    now = datetime.now().strftime(fmt)
    tz = time.strftime("%Z") or "UTC"
    return f"{now} ({tz})"


def build_runtime_block(*, channel: str | None = None, chat_id: str | None = None) -> str:
    system = platform.system()
    runtime_lines = [
        f"Host: {'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}",
        f"Current time: {format_current_time()}",
    ]
    if channel and chat_id:
        runtime_lines.append(f"Channel: {channel} | Chat: {chat_id}")
    elif channel:
        runtime_lines.append(f"Channel: {channel}")
    return "\n".join(runtime_lines)


CHANNEL_FORMAT_HINTS: dict[str, str] = {
    "telegram": (
        "Response Format: This channel renders Markdown well (converted to HTML). "
        "You may freely use bold, italic, code blocks, inline code, links, and bullet lists. "
        "Avoid HTML tags — use standard Markdown only."
    ),
    "discord": (
        "Response Format: This channel natively renders Markdown. "
        "You may use bold, italic, strikethrough, code blocks, inline code, links, "
        "bullet lists, and numbered lists. Avoid headings (#) — Discord does not render them."
    ),
    "slack": (
        "Response Format: This channel uses Slack mrkdwn (not standard Markdown). "
        "Use *bold*, _italic_, `inline code`, and ```code blocks```. "
        "Use bullet lists with • or -. Do NOT use headings (#), nested lists, or Markdown tables. "
        "Links: use <url|text> format or just paste the URL."
    ),
    "feishu": (
        "Response Format: This channel renders Feishu card Markdown (a subset of standard Markdown). "
        "You may use **bold**, *italic*, `inline code`, ```code blocks```, links, and bullet lists. "
        "Markdown tables are supported. Avoid deeply nested structures. "
        "Do NOT use headings (#) — they will be converted to bold text."
    ),
    "dingtalk": (
        "Response Format: This channel supports DingTalk Markdown (a limited subset). "
        "You may use headings (#), **bold**, links, images, and ordered/unordered lists. "
        "Do NOT use italic, strikethrough, tables, or code blocks — they may not render correctly."
    ),
    "whatsapp": (
        "Response Format: This channel has very limited formatting. "
        "Use *bold*, _italic_, ~strikethrough~, and ```code blocks``` (WhatsApp syntax). "
        "Do NOT use Markdown headings (#), links [text](url), bullet symbols, or tables. "
        "Use plain line breaks and simple numbered lists (1. 2. 3.) for structure."
    ),
    "qq": (
        "Response Format: This channel does NOT support Markdown or rich text. "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Use blank lines to separate sections. Do NOT use any Markdown syntax."
    ),
    "imessage": (
        "Response Format: This channel does NOT support Markdown or rich text. "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Keep paragraphs short. Do NOT use any Markdown syntax — it will display as raw characters."
    ),
    "email": (
        "Response Format: This channel sends plain text emails (not HTML). "
        "Use plain text only. Use simple symbols like •, -, > for structure. "
        "Do NOT use any Markdown syntax — it will appear as raw characters in the email."
    ),
}


class LazyMemoryStoreProxy:
    def __init__(
        self,
        storage_root: Path,
        options: LazyMemoryStoreOptions,
    ):
        object.__setattr__(self, "_storage_root", storage_root)
        object.__setattr__(self, "_memory_store_cls", options.memory_store_cls)
        object.__setattr__(self, "_embedding_config", options.embedding_config)
        object.__setattr__(self, "_memory_policy", options.memory_policy)
        object.__setattr__(self, "_lock", threading.RLock())
        object.__setattr__(self, "_store", None)

    def _get_store(self) -> Any:
        store = object.__getattribute__(self, "_store")
        if store is not None:
            return store
        lock = object.__getattribute__(self, "_lock")
        with lock:
            store = object.__getattribute__(self, "_store")
            if store is not None:
                return store
            memory_store_cls = object.__getattribute__(self, "_memory_store_cls")
            init_kwargs = {"embedding_config": object.__getattribute__(self, "_embedding_config")}
            memory_policy = object.__getattribute__(self, "_memory_policy")
            try:
                accepts_memory_policy = "memory_policy" in inspect.signature(memory_store_cls).parameters
            except (TypeError, ValueError):
                accepts_memory_policy = False
            if accepts_memory_policy:
                init_kwargs["memory_policy"] = memory_policy
            store = memory_store_cls(object.__getattribute__(self, "_storage_root"), **init_kwargs)
            object.__setattr__(self, "_store", store)
            return store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_store(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._get_store(), name, value)

    def __dir__(self) -> list[str]:
        names = set(super().__dir__())
        store = object.__getattribute__(self, "_store")
        if store is not None:
            names.update(dir(store))
        return sorted(names)

    def close(self) -> None:
        lock = object.__getattribute__(self, "_lock")
        with lock:
            store = object.__getattribute__(self, "_store")
            if store is None:
                return
            close = getattr(store, "close", None)
            if callable(close):
                close()
            object.__setattr__(self, "_store", None)
