"""Chat commands: /model and /session handlers.

Extracted from loop.py to isolate interactive command logic from the
main message loop.  All functions are stateless module-level helpers;
mutable state is passed explicitly via parameters.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from loguru import logger

from bao.bus.events import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from bao.session.manager import Session, SessionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def reply(msg: InboundMessage, content: str) -> OutboundMessage:
    metadata = dict(msg.metadata) if isinstance(msg.metadata, dict) else {}
    reply_to = metadata.get("reply_to")
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=content,
        reply_to=reply_to if isinstance(reply_to, str) else None,
        metadata=metadata,
    )


def format_session_name(key: str, natural_key: str) -> str:
    if key == natural_key:
        return "default"
    prefix = f"{natural_key}::"
    return key[len(prefix) :] if key.startswith(prefix) else key


def format_relative_time(updated: str | None) -> str:
    if not updated:
        return ""
    raw = str(updated)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        now = datetime.now(tz=dt.tzinfo)
        secs = max(0, int((now - dt).total_seconds()))
        if secs < 60:
            return " (刚刚)"
        if secs < 3600:
            return f" ({secs // 60}分钟前)"
        if secs < 86400:
            return f" ({secs // 3600}小时前)"
        if secs < 172800:
            return " (昨天)"
        days = secs // 86400
        if days < 7:
            return f" ({days}天前)"
        if dt.year == now.year:
            return f" ({dt.month}月{dt.day}日)"
        return f" ({dt.strftime('%Y-%m-%d')})"
    except Exception:
        return f" ({raw[:16]})"


def create_and_switch(sessions: SessionManager, natural_key: str, name: str) -> str:
    key = f"{natural_key}::{name}"
    sessions.save(sessions.get_or_create(key))
    sessions.set_active_session_key(natural_key, key)
    return name


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------


def handle_model_command(
    cmd: str,
    msg: InboundMessage,
    session: Session,
    *,
    available_models: list[str],
    current_model: str,
    sessions: SessionManager,
    apply_fn: Callable[[str], None] | None = None,
) -> OutboundMessage:
    """Show model list or switch by index."""
    _, _, arg = cmd.partition(" ")
    if arg.isdigit():
        return switch_model(
            int(arg),
            msg,
            session,
            available_models=available_models,
            current_model=current_model,
            sessions=sessions,
            apply_fn=apply_fn,
        )

    if not available_models:
        return reply(
            msg,
            f"Current model: `{current_model}`\n\nNo alternative models configured. Add `models` list to config.",
        )

    lines = [f"Current model: `{current_model}`\n"]
    lines += [
        f"  {i}. {m}{' ✓' if m == current_model else ''}" for i, m in enumerate(available_models, 1)
    ]
    lines.append("\nReply with a number to switch.")

    session.metadata["_pending_model_select"] = True
    sessions.save(session)
    return reply(msg, "\n".join(lines))


def switch_model(
    idx: int,
    msg: InboundMessage,
    session: Session,
    *,
    available_models: list[str],
    current_model: str,
    sessions: SessionManager,
    apply_fn: Callable[[str], None] | None = None,
) -> OutboundMessage:
    """Validate and switch model. Call apply_fn(new_model) for mutation."""
    if idx < 1 or idx > len(available_models):
        return reply(msg, f"Invalid selection. Choose 1-{len(available_models)}.")

    new_model = available_models[idx - 1]
    if apply_fn is None:
        logger.debug("switch_model called without apply_fn, model not actually changed")
        return reply(msg, "模型切换失败：缺少 apply_fn 回调。")
    try:
        apply_fn(new_model)
    except Exception as e:
        logger.warning("⚠️ Provider 重建失败 / rebuild failed for {}: {}", new_model, e)
        return reply(msg, f"模型切换失败，仍为 `{current_model}`。错误: {e}")

    sessions.save(session)
    return reply(msg, f"Model switched to `{new_model}`")


# ---------------------------------------------------------------------------
# /session
# ---------------------------------------------------------------------------


def handle_session_command(
    msg: InboundMessage,
    natural_key: str,
    *,
    sessions: SessionManager,
) -> OutboundMessage:
    """Show numbered session list for selection."""
    all_sessions = sessions.list_sessions_for(natural_key) or [
        {"key": natural_key, "updated_at": None}
    ]
    active = sessions.get_active_session_key(natural_key)
    current_key = active or natural_key

    lines = ["📋 会话列表:\n  0. 取消\n"]
    session_keys: list[str] = []
    for i, s in enumerate(all_sessions, 1):
        skey = str(s.get("key") or natural_key)
        session_keys.append(skey)
        metadata = s.get("metadata") or {}
        title = metadata.get("title")
        name = title or format_session_name(skey, natural_key)
        marker = " ✓" if skey == current_key else ""
        ts = format_relative_time(s.get("updated_at"))
        lines.append(f"  {i}. {name}{marker}{ts}")
    lines.append("\n输入数字选择，/new 创建新会话")

    default_session = sessions.get_or_create(current_key)
    default_session.metadata["_pending_session_select"] = True
    default_session.metadata["_session_list_keys"] = session_keys
    sessions.save(default_session)

    return reply(msg, "\n".join(lines))


def select_session(
    idx: int,
    msg: InboundMessage,
    natural_key: str,
    *,
    sessions: SessionManager,
    cached_keys: list[str] | None = None,
) -> OutboundMessage:
    """Switch to the session at the given index."""
    if idx == 0:
        return reply(msg, "已取消 👌")

    if cached_keys:
        keys = cached_keys
    else:
        all_sessions = sessions.list_sessions_for(natural_key) or [
            {"key": natural_key, "updated_at": None}
        ]
        keys = [str(s.get("key") or natural_key) for s in all_sessions]

    if idx < 1 or idx > len(keys):
        return reply(msg, f"无效选择，请输入 0-{len(keys)}")

    selected_key = keys[idx - 1]

    active = sessions.get_active_session_key(natural_key)
    current_key = active or natural_key
    if selected_key == current_key:
        return reply(msg, "已在当前会话 👌")

    if selected_key == natural_key:
        sessions.clear_active_session_key(natural_key)
    else:
        sessions.set_active_session_key(natural_key, selected_key)

    target = sessions.get_or_create(selected_key)
    title = target.metadata.get("title")
    name = title or format_session_name(selected_key, natural_key)
    return reply(msg, f"已切换到会话「{name}」 🔄")
