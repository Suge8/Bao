"""Shared gateway stack builder — no UI framework dependencies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any


@dataclass
class GatewayStack:
    config: Any
    bus: Any
    session_manager: Any
    cron: Any
    heartbeat: Any
    agent: Any
    channels: Any


def build_gateway_stack(config: Any, provider: Any) -> GatewayStack:
    """Build the full gateway service stack from config and provider.

    Returns a :class:`GatewayStack` with all services wired up and ready to start.
    """
    from bao.agent.loop import AgentLoop
    from bao.bus.events import OutboundMessage
    from bao.bus.queue import MessageBus
    from bao.channels.manager import ChannelManager
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService
    from bao.cron.types import CronJob
    from bao.heartbeat.service import HeartbeatService
    from bao.session.manager import SessionManager

    bus = MessageBus()
    session_manager = SessionManager(config.workspace_path)
    cron = CronService(get_data_dir() / "cron" / "jobs.json")

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy,
        exec_config=config.tools.exec,
        cron_service=cron,
        embedding_config=config.tools.embedding,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        available_models=config.agents.defaults.models,
        config=config,
    )

    # --- cron callback (defensive, from Desktop version) ---
    async def on_cron_job(job: CronJob) -> str | None:
        from loguru import logger

        try:
            reminder_note = (
                "[Scheduled Task] Timer finished.\n\n"
                f"Task '{job.name}' has been triggered.\n"
                f"Scheduled instruction: {job.payload.message}"
            )
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "gateway",
                chat_id=job.payload.to or "direct",
            )
        except Exception as e:
            logger.warning("⚠️ 定时任务失败 / cron failed: {} — {}", job.id, e)
            return f"Error: {e}"
        if job.payload.deliver and job.payload.to:
            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "gateway",
                    chat_id=job.payload.to,
                    content=response or "",
                )
            )
        return response

    cron.on_job = on_cron_job

    def _extract_primary_id(raw_uid: Any) -> str:
        return str(raw_uid or "").split("|", 1)[0].strip()

    def _is_telegram_chat_id(chat_id: str) -> bool:
        return bool(chat_id) and chat_id.lstrip("-").isdigit()

    def _iter_heartbeat_targets() -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []

        for ch_name in ("telegram", "feishu", "dingtalk", "qq", "imessage", "email"):
            ch_cfg = getattr(config.channels, ch_name, None)
            if not (
                ch_cfg and getattr(ch_cfg, "enabled", False) and getattr(ch_cfg, "allow_from", None)
            ):
                continue
            chat_id = _extract_primary_id(ch_cfg.allow_from[0])
            if ch_name == "telegram" and not _is_telegram_chat_id(chat_id):
                continue
            if chat_id:
                targets.append((ch_name, chat_id))

        wa_cfg = getattr(config.channels, "whatsapp", None)
        if wa_cfg and getattr(wa_cfg, "enabled", False) and getattr(wa_cfg, "allow_from", None):
            bare = _extract_primary_id(wa_cfg.allow_from[0])
            if bare:
                wa_chat_id = bare if "@" in bare else f"{bare}@s.whatsapp.net"
                targets.append(("whatsapp", wa_chat_id))

        return targets

    # --- heartbeat ---
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = "cli", "direct"
        targets = _iter_heartbeat_targets()
        if targets:
            channel, chat_id = targets[0]

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver heartbeat result to the first available channel."""
        targets = _iter_heartbeat_targets()
        if not targets:
            return

        ch_name, chat_id = targets[0]
        await bus.publish_outbound(
            OutboundMessage(channel=ch_name, chat_id=chat_id, content=response)
        )

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    channels = ChannelManager(config, bus)

    return GatewayStack(
        config=config,
        bus=bus,
        session_manager=session_manager,
        cron=cron,
        heartbeat=heartbeat,
        agent=agent,
        channels=channels,
    )


async def send_startup_greeting(
    agent: Any,
    bus: Any,
    config: Any,
    *,
    on_desktop_greeting: Any | None = None,
) -> None:
    """Send startup greeting to all enabled channels.
    Each channel gets an independent LLM call with its own session context.
    Channels where allow_from != chat_id are skipped (discord/slack/mochat).
    """
    from loguru import logger

    from bao.bus.events import OutboundMessage

    async def _emit_desktop_greeting(content: str, phase: str) -> None:
        if not on_desktop_greeting:
            return
        try:
            maybe = on_desktop_greeting(content)
            if isawaitable(maybe):
                await maybe
        except Exception as e:
            logger.warning("⚠️ 桌面回调失败 / callback failed: {} — {}", phase, e)

    await asyncio.sleep(5)

    def _extract_primary_id(raw_uid: Any) -> str:
        return str(raw_uid or "").split("|", 1)[0].strip()

    def _is_telegram_chat_id(chat_id: str) -> bool:
        return bool(chat_id) and chat_id.lstrip("-").isdigit()

    targets: list[tuple[str, str]] = []
    seen_targets: set[tuple[str, str]] = set()

    def _add_target(channel_name: str, chat_id: str) -> None:
        if not chat_id:
            logger.warning("⚠️ 问候目标跳过 / target skipped: {} empty chat_id", channel_name)
            return
        pair = (channel_name, chat_id)
        if pair in seen_targets:
            return
        seen_targets.add(pair)
        targets.append(pair)

    # Channels where allow_from directly maps to chat_id
    channel_cfgs = [
        ("telegram", config.channels.telegram),
        ("feishu", config.channels.feishu),
        ("dingtalk", config.channels.dingtalk),
        ("imessage", config.channels.imessage),
        ("qq", config.channels.qq),
        ("email", config.channels.email),
    ]
    for name, cfg in channel_cfgs:
        if not (cfg.enabled and cfg.allow_from):
            continue
        for uid in cfg.allow_from:
            target = _extract_primary_id(uid)
            if name == "telegram" and not _is_telegram_chat_id(target):
                continue
            _add_target(name, target)

    # WhatsApp: phone -> JID (skip if already a JID)
    wa = config.channels.whatsapp
    if wa.enabled and wa.allow_from:
        for uid in wa.allow_from:
            bare = _extract_primary_id(uid)
            if not bare:
                logger.warning("⚠️ 问候目标跳过 / target skipped: whatsapp empty id")
                continue
            jid = bare if "@" in bare else f"{bare}@s.whatsapp.net"
            _add_target("whatsapp", jid)

    from bao.config.onboarding import (
        LANG_PICKER,
        PERSONA_GREETING,
        detect_onboarding_stage,
        infer_language,
    )

    stage = detect_onboarding_stage(config.workspace_path)

    # Onboarding: broadcast static messages (no session needed)
    if stage in ("lang_select", "persona_setup"):
        if stage == "lang_select":
            content = LANG_PICKER
        else:
            lang = infer_language(config.workspace_path)
            content = PERSONA_GREETING.get(lang, PERSONA_GREETING["en"])
        for ch, cid in targets:
            try:
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=content)
                )
            except Exception as e:
                logger.warning("⚠️ 入门问候失败 / onboarding failed: {}:{} — {}", ch, cid, e)
        await _emit_desktop_greeting(content, "Onboarding")
        return

    # Ready stage: personalized greeting per channel
    prompt = (
        "You just came online. Greet the user in character based on your "
        "PERSONA.md personality. Mention the current time naturally. "
        "Don't self-introduce. Keep it short, like an old friend saying hi."
    )

    async def _generate_and_clean(session_key: str, channel: str, chat_id: str) -> str | None:
        """Generate greeting and remove the prompt from session history."""
        active = agent.sessions.get_active_session_key(session_key)
        resolved = active or session_key
        session = agent.sessions.get_or_create(resolved)
        n_before = len(session.messages)
        try:
            text = await agent.process_direct(
                prompt,
                session_key=resolved,
                channel=channel,
                chat_id=chat_id,
                ephemeral=True,
            )
        except Exception as e:
            logger.warning("⚠️ 启动问候失败 / startup failed: {}:{} — {}", channel, chat_id, e)
            return None
        if not text:
            return None
        # Remove only the injected prompt message, keep everything else
        try:
            session = agent.sessions.get_or_create(resolved)
            for i in range(n_before, len(session.messages)):
                msg = session.messages[i]
                content = msg.get("content", "")
                if msg.get("role") != "user":
                    continue
                if content == prompt:
                    removed = session.messages.pop(i)
                    try:
                        agent.sessions.save(session)
                    except Exception as e:
                        session.messages.insert(i, removed)
                        logger.warning(
                            "⚠️ 提示清理落库失败 / cleanup persist failed: {}:{} — {}",
                            channel,
                            chat_id,
                            e,
                        )
                    break
        except Exception as e:
            logger.warning("⚠️ 提示清理失败 / cleanup failed: {}:{} — {}", channel, chat_id, e)
        return text

    # External channels
    for ch, cid in targets:
        text = await _generate_and_clean(f"{ch}:{cid}", ch, cid)
        if text:
            try:
                await bus.publish_outbound(OutboundMessage(channel=ch, chat_id=cid, content=text))
            except Exception as e:
                logger.warning("⚠️ 问候发送失败 / send failed: {}:{} — {}", ch, cid, e)

    # Desktop channel (not in ChannelManager, uses callback)
    if on_desktop_greeting:
        text = await _generate_and_clean("desktop:local", "desktop", "local")
        if text:
            await _emit_desktop_greeting(text, "Desktop startup")


async def shutdown_gateway_stack(stack: GatewayStack, background_tasks: list[Any]) -> None:
    """Shutdown all gateway services. Mirrors CLI finally block."""
    for t in background_tasks:
        t.cancel()
    if stack.agent:
        await stack.agent.close_mcp()
    if stack.heartbeat:
        stack.heartbeat.stop()
    if stack.cron:
        stack.cron.stop()
    if stack.agent:
        stack.agent.stop()
    if stack.channels:
        await stack.channels.stop_all()
