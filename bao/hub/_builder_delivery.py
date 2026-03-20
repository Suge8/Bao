from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import Any


@dataclass(frozen=True)
class StartupDelivery:
    channel_name: str
    chat_id: str
    content: str
    entrance_style: str


@dataclass(frozen=True)
class CallbackInvocation:
    callback: Any
    logger: Any
    payload: Any
    phase: str


def build_startup_activity(targets: tuple[tuple[str, str], ...], has_desktop: bool) -> dict[str, Any]:
    channel_keys: list[str] = []
    session_keys: list[str] = []
    if has_desktop:
        channel_keys.append("desktop")
        session_keys.append("desktop:local")
    for channel_name, chat_id in targets:
        if channel_name not in channel_keys:
            channel_keys.append(channel_name)
        session_key = f"{channel_name}:{chat_id}"
        if session_key not in session_keys:
            session_keys.append(session_key)
    return {
        "kind": "startup_greeting",
        "status": "running",
        "channelKeys": channel_keys,
        "sessionKeys": session_keys,
    }


def log_startup_out(logger: Any, delivery: StartupDelivery, *, delivered: bool) -> None:
    preview = delivery.content[:60] + "..." if len(delivery.content) > 60 else delivery.content
    preview = preview.replace("\n", " ")
    status = "已发送 / sent" if delivered else "已入队 / queued"
    logger.info(
        "💬 启动问候{}: {}:{}: {}",
        status,
        delivery.channel_name,
        delivery.chat_id,
        preview,
    )


def persist_startup_message(session_manager: Any, delivery: StartupDelivery) -> None:
    if session_manager is None or not delivery.content:
        return
    natural_key = f"{delivery.channel_name}:{delivery.chat_id}"
    session_key = session_manager.resolve_active_session_key(natural_key)
    session = session_manager.get_or_create(session_key)
    session.add_message(
        "assistant",
        delivery.content,
        status="done",
        format="markdown",
        entrance_style=delivery.entrance_style,
    )
    session_manager.save(session)
    session_manager.mark_desktop_seen_ai_if_active(session_key)


async def _emit_callback(invocation: CallbackInvocation) -> None:
    if invocation.callback is None:
        return
    try:
        result = invocation.callback(invocation.payload)
        if isawaitable(result):
            await result
    except Exception as exc:
        invocation.logger.warning("⚠️ 启动回调失败 / startup callback failed: {} — {}", invocation.phase, exc)


async def emit_callback(invocation: CallbackInvocation) -> None:
    await _emit_callback(invocation)
