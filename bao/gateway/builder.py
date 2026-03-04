"""Shared gateway stack builder — no UI framework dependencies."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from inspect import isawaitable
from pathlib import Path
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


def _extract_primary_id(raw_uid: Any) -> str:
    return str(raw_uid or "").split("|", 1)[0].strip()


def _is_telegram_chat_id(chat_id: str) -> bool:
    return bool(chat_id) and chat_id.lstrip("-").isdigit()


def _collect_startup_targets(config: Any, logger: Any) -> list[tuple[str, str]]:
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

    wa = config.channels.whatsapp
    if wa.enabled and wa.allow_from:
        for uid in wa.allow_from:
            bare = _extract_primary_id(uid)
            if not bare:
                logger.warning("⚠️ 问候目标跳过 / target skipped: whatsapp empty id")
                continue
            jid = bare if "@" in bare else f"{bare}@s.whatsapp.net"
            _add_target("whatsapp", jid)

    return targets


def _log_startup_out(logger: Any, channel_name: str, chat_id: str, content: str) -> None:
    preview = content[:60] + "..." if len(content) > 60 else content
    preview = preview.replace("\n", " ")
    logger.info("💬 启动问候 / out: {}:{}: {}", channel_name, chat_id, preview)


def _extract_persona_language_tag(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.search(r"(?:\*\*\s*)?(?:language|lang|语言)(?:\s*\*\*)?\s*[:：]\s*(.+)$", line, re.I)
        if not m:
            continue
        value = m.group(1).strip().strip("`*")
        return value or None
    return None


def _read_persona_text(workspace_path: Path, logger: Any) -> str:
    try:
        persona_path = workspace_path / "PERSONA.md"
        if persona_path.exists():
            return persona_path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("⚠️ 读取 PERSONA 失败 / read failed: {}", e)
    return ""


def _build_local_time(preferred_language: str, now_local: datetime) -> str:
    zh_weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    ja_weekdays = ["月曜", "火曜", "水曜", "木曜", "金曜", "土曜", "日曜"]
    ko_weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    en_weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lang_lower = preferred_language.lower()
    if any(k in lang_lower for k in ("中文", "chinese", "mandarin")):
        weekdays = zh_weekdays
    elif any(k in lang_lower for k in ("日本語", "japanese")):
        weekdays = ja_weekdays
    elif any(k in lang_lower for k in ("한국어", "korean")):
        weekdays = ko_weekdays
    else:
        weekdays = en_weekdays
    return f"{weekdays[now_local.weekday()]} {now_local.strftime('%H:%M')}"


def _build_startup_prompt(preferred_language: str, local_time: str) -> str:
    native_triggers: dict[str, str] = {
        "中文": "我来啦，{t}",
        "chinese": "我来啦，{t}",
        "mandarin": "我来啦，{t}",
        "日本語": "来たよ、{t}",
        "japanese": "来たよ、{t}",
        "한국어": "왔어요, {t}",
        "korean": "왔어요, {t}",
    }
    lang_lower = preferred_language.lower()
    trigger_tpl = next(
        (v for k, v in native_triggers.items() if k in lang_lower),
        "I just came online. It's {t}.",
    )
    return trigger_tpl.format(t=local_time)


def _build_startup_system_prompt(persona_text: str, preferred_language: str) -> str:
    system_parts: list[str] = []
    if persona_text:
        system_parts.append(f"## PERSONA.md\n{persona_text}")
    system_parts.append(
        f"User just came online. Respond in {preferred_language}. "
        "Greet like a close friend — casual, warm, 1-2 sentences. "
        "Naturally weave in the day/time. "
        "Do NOT ask questions, offer help, or list capabilities."
    )
    return "\n\n---\n\n".join(system_parts)


async def _generate_startup_greeting(
    agent: Any,
    logger: Any,
    *,
    system_prompt: str,
    prompt: str,
    channel: str,
    chat_id: str,
) -> str | None:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    try:
        response = await agent.provider.chat(
            messages=messages,
            model=getattr(agent, "model", None),
            max_tokens=200,
            temperature=0.7,
        )
        text = (response.content or "").strip()
        if text:
            return text
        raise RuntimeError("empty startup greeting")
    except Exception as e:
        logger.warning(
            "⚠️ 启动问候轻量生成失败 / lightweight startup failed: {}:{} — {}",
            channel,
            chat_id,
            e,
        )
        try:
            text = await agent.process_direct(
                prompt,
                session_key=f"{channel}:{chat_id}",
                channel=channel,
                chat_id=chat_id,
                ephemeral=True,
            )
        except Exception as e2:
            logger.warning("⚠️ 启动问候失败 / startup failed: {}:{} — {}", channel, chat_id, e2)
            return None
    if not text:
        return None
    return text


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

    async def _send_external_greeting(
        channel_name: str,
        chat_id: str,
        *,
        system_prompt: str,
        prompt: str,
    ) -> None:
        text = await _generate_startup_greeting(
            agent,
            logger,
            system_prompt=system_prompt,
            prompt=prompt,
            channel=channel_name,
            chat_id=chat_id,
        )
        if not text:
            return
        try:
            await bus.publish_outbound(
                OutboundMessage(channel=channel_name, chat_id=chat_id, content=text)
            )
            _log_startup_out(logger, channel_name, chat_id, text)
        except Exception as e:
            logger.warning("⚠️ 问候发送失败 / send failed: {}:{} — {}", channel_name, chat_id, e)

    async def _send_external_greetings(*, system_prompt: str, prompt: str) -> None:
        for ch, cid in targets:
            await _send_external_greeting(
                ch,
                cid,
                system_prompt=system_prompt,
                prompt=prompt,
            )

    async def _broadcast_onboarding(content: str) -> None:
        for ch, cid in targets:
            try:
                await bus.publish_outbound(
                    OutboundMessage(channel=ch, chat_id=cid, content=content)
                )
                _log_startup_out(logger, ch, cid, content)
            except Exception as e:
                logger.warning("⚠️ 入门问候失败 / onboarding failed: {}:{} — {}", ch, cid, e)

    async def _send_desktop_greeting(*, system_prompt: str, prompt: str) -> None:
        text = await _generate_startup_greeting(
            agent,
            logger,
            system_prompt=system_prompt,
            prompt=prompt,
            channel="desktop",
            chat_id="local",
        )
        if text:
            await _emit_desktop_greeting(text, "Desktop startup")

    await asyncio.sleep(5)
    targets = _collect_startup_targets(config, logger)

    from bao.config.onboarding import (
        LANG_PICKER,
        PERSONA_GREETING,
        detect_onboarding_stage,
        infer_language,
    )

    workspace_path = Path(str(config.workspace_path)).expanduser()
    stage = detect_onboarding_stage(workspace_path)

    # Onboarding: broadcast static messages (no session needed)
    if stage in ("lang_select", "persona_setup"):
        if stage == "lang_select":
            content = LANG_PICKER
        else:
            lang = infer_language(workspace_path)
            content = PERSONA_GREETING.get(lang, PERSONA_GREETING["en"])
        if on_desktop_greeting:
            await asyncio.gather(
                _broadcast_onboarding(content),
                _emit_desktop_greeting(content, "Onboarding"),
            )
        else:
            await _broadcast_onboarding(content)
        return

    # Ready stage: personalized greeting per channel
    now_local = datetime.now().astimezone()
    persona_text = _read_persona_text(workspace_path, logger)

    persona_lang_tag = _extract_persona_language_tag(persona_text) if persona_text else None
    preferred_language = persona_lang_tag or infer_language(workspace_path)
    local_time = _build_local_time(preferred_language, now_local)
    prompt = _build_startup_prompt(preferred_language, local_time)
    system_prompt = _build_startup_system_prompt(persona_text, preferred_language)

    if on_desktop_greeting:
        await asyncio.gather(
            _send_external_greetings(system_prompt=system_prompt, prompt=prompt),
            _send_desktop_greeting(system_prompt=system_prompt, prompt=prompt),
        )
    else:
        await _send_external_greetings(system_prompt=system_prompt, prompt=prompt)


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
