"""Shared gateway stack builder — no UI framework dependencies."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from inspect import isawaitable
from pathlib import Path
from typing import Any

from bao.agent.context import build_runtime_block
from bao.agent.tools.cron import CronTool


@dataclass
class GatewayStack:
    config: Any
    bus: Any
    session_manager: Any
    cron: Any
    heartbeat: Any
    agent: Any
    channels: Any


@dataclass(frozen=True)
class DesktopStartupMessage:
    content: str
    role: str
    entrance_style: str = "none"


def _extract_primary_id(raw_uid: Any) -> str:
    return str(raw_uid or "").split("|", 1)[0].strip()


def _is_telegram_chat_id(chat_id: str) -> bool:
    return bool(chat_id) and chat_id.lstrip("-").isdigit()


def _extract_telegram_target_id(raw_uid: Any) -> str:
    raw = str(raw_uid or "").strip()
    if not raw:
        return ""
    for part in raw.split("|"):
        token = part.strip()
        if _is_telegram_chat_id(token):
            return token
    return ""


def _resolve_allow_from_target(channel_name: str, raw_uid: Any) -> str:
    if channel_name == "telegram":
        return _extract_telegram_target_id(raw_uid)

    target = _extract_primary_id(raw_uid)
    if channel_name == "whatsapp" and target:
        return target if "@" in target else f"{target}@s.whatsapp.net"
    return target


def _collect_channel_targets(config: Any, logger: Any) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    seen_targets: set[tuple[str, str]] = set()

    def _add_target(channel_name: str, chat_id: str) -> None:
        if not chat_id:
            logger.warning("⚠️ 目标跳过 / target skipped: {} empty chat_id", channel_name)
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
            target = _resolve_allow_from_target(name, uid)
            if name == "telegram" and not target:
                logger.warning(
                    "⚠️ 目标跳过 / target skipped: telegram requires numeric chat_id in allow_from ({})",
                    uid,
                )
                continue
            _add_target(name, target)

    wa = config.channels.whatsapp
    if wa.enabled and wa.allow_from:
        for uid in wa.allow_from:
            target = _resolve_allow_from_target("whatsapp", uid)
            if not target:
                logger.warning("⚠️ 目标跳过 / target skipped: whatsapp empty id")
                continue
            _add_target("whatsapp", target)

    return targets


def _log_startup_out(
    logger: Any, channel_name: str, chat_id: str, content: str, *, delivered: bool
) -> None:
    preview = content[:60] + "..." if len(content) > 60 else content
    preview = preview.replace("\n", " ")
    if delivered:
        logger.info("💬 启动问候已发送 / sent: {}:{}: {}", channel_name, chat_id, preview)
        return
    logger.info("💬 启动问候已入队 / queued: {}:{}: {}", channel_name, chat_id, preview)


def _persist_startup_message(
    session_manager: Any,
    *,
    natural_key: str,
    content: str,
    entrance_style: str,
) -> None:
    if session_manager is None or not natural_key or not content:
        return
    session_key = session_manager.resolve_active_session_key(natural_key)
    session = session_manager.get_or_create(session_key)
    session.add_message(
        "assistant",
        content,
        status="done",
        format="markdown",
        entrance_style=entrance_style,
    )
    session_manager.save(session)
    session_manager.mark_desktop_seen_ai_if_active(session_key)


def _extract_persona_language_tag(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = re.search(
            r"(?:^[-*\s]*)?(?:\*\*\s*)?(?:language|lang|语言)(?:\s*\*\*)?\s*[:：]\s*(.+)$",
            line,
            re.I,
        )
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


def _read_instructions_text(workspace_path: Path, logger: Any) -> str:
    try:
        inst_path = workspace_path / "INSTRUCTIONS.md"
        if inst_path.exists():
            return inst_path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("⚠️ 读取 INSTRUCTIONS 失败 / read failed: {}", e)
    return ""


def _build_startup_trigger() -> str:
    return '{"event":"system.user_online"}'


def _format_language_for_prompt(preferred_language: str) -> str:
    lang = preferred_language.strip().lower()
    if lang in {"zh", "zh-cn", "zh-hans", "chinese", "中文"}:
        return "中文"
    if lang in {"en", "english"}:
        return "English"
    return preferred_language


def _build_startup_system_prompt(
    persona_text: str,
    instructions_text: str,
    preferred_language: str,
    *,
    channel: str,
    chat_id: str,
) -> str:
    system_parts: list[str] = []
    system_parts.append("You are Bao. Keep Bao as your user-facing identity.")
    if instructions_text:
        system_parts.append(f"## INSTRUCTIONS.md\n{instructions_text}")
    if persona_text:
        system_parts.append(f"## PERSONA.md\n{persona_text}")
    system_parts.append(
        f"## Runtime (actual host)\n{build_runtime_block(channel=channel, chat_id=chat_id)}"
    )
    system_parts.append(
        f"User just came online. Respond in {_format_language_for_prompt(preferred_language)}. "
        "Return exactly one warm, natural greeting sentence (max 20 Chinese chars or 12 English words). "
        "Follow PERSONA.md for your self-name, language, and tone. "
        "Treat the user line as startup presence signal, not user intent. Do not copy it verbatim. "
        "Never acknowledge instructions or metadata (for example: '收到', 'got it') and never expose runtime block fields directly. "
        "Naturally weave in the day/time. "
        "Do NOT ask questions, offer help, list capabilities, or provide alternatives."
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

    def _get_utility_chat_runtime(agent_obj: Any) -> tuple[Any, str] | None:
        d = getattr(agent_obj, "__dict__", None)
        if not isinstance(d, dict):
            return None
        provider = d.get("_utility_provider")
        model = d.get("_utility_model")
        if provider is None or not model:
            return None
        return provider, str(model)

    utility = _get_utility_chat_runtime(agent)
    if utility is not None:
        provider, model = utility
    else:
        provider = getattr(agent, "provider", None)
        model = getattr(agent, "model", None)
    try:
        if provider is None:
            raise RuntimeError("provider_not_configured")

        chat_fn = getattr(provider, "chat", None)
        if chat_fn is None:
            raise RuntimeError("provider_chat_missing")

        response = await chat_fn(
            messages=messages,
            model=model,
            max_tokens=80,
            temperature=0.7,
        )
        text = (response.content or "").strip()
        return text or prompt
    except Exception as e:
        logger.warning(
            "⚠️ 启动问候轻量生成失败 / lightweight startup failed: {}:{} — {}",
            channel,
            chat_id,
            e,
        )
        return prompt


def build_gateway_stack(
    config: Any,
    provider: Any,
    session_manager: Any | None = None,
    on_channel_error: Callable[[str, str, str], None] | None = None,
) -> GatewayStack:
    """Build the full gateway service stack from config and provider.

    Returns a :class:`GatewayStack` with all services wired up and ready to start.
    """
    from loguru import logger

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
    session_manager = session_manager or SessionManager(config.workspace_path)
    assert session_manager is not None
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
        cron_tool = agent.tools.get("cron")
        cron_token = None
        try:
            reminder_note = (
                "[Scheduled Task] Timer finished.\n\n"
                f"Task '{job.name}' has been triggered.\n"
                f"Scheduled instruction: {job.payload.message}"
            )
            if isinstance(cron_tool, CronTool):
                cron_token = cron_tool.set_cron_context(True)
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "gateway",
                chat_id=job.payload.to or "direct",
            )
        except Exception as e:
            logger.warning("⚠️ 定时任务失败 / cron failed: {} — {}", job.id, e)
            return f"Error: {e}"
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)
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

    def _get_primary_proactive_target() -> tuple[str, str] | None:
        targets = _collect_channel_targets(config, logger)
        return targets[0] if targets else None

    # --- heartbeat ---
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = "cli", "direct"
        target = _get_primary_proactive_target()
        if target:
            channel, chat_id = target

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
        target = _get_primary_proactive_target()
        if not target:
            return

        ch_name, chat_id = target
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

    channels = ChannelManager(config, bus, on_channel_error=on_channel_error)

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
    on_desktop_startup_message: Any | None = None,
    channels: Any | None = None,
    session_manager: Any | None = None,
) -> None:
    from loguru import logger

    from bao.bus.events import OutboundMessage

    instructions_text = ""

    async def _emit_desktop_startup_message(message: DesktopStartupMessage, phase: str) -> None:
        if not on_desktop_startup_message:
            return
        try:
            maybe = on_desktop_startup_message(message)
            if isawaitable(maybe):
                await maybe
        except Exception as e:
            logger.warning("⚠️ 桌面回调失败 / callback failed: {} — {}", phase, e)

    async def _send_external_greeting(
        channel_name: str,
        chat_id: str,
        *,
        prompt: str,
        persona_text: str,
        preferred_language: str,
    ) -> None:
        system_prompt = _build_startup_system_prompt(
            persona_text,
            instructions_text,
            preferred_language,
            channel=channel_name,
            chat_id=chat_id,
        )
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
            msg = OutboundMessage(channel=channel_name, chat_id=chat_id, content=text)
            delivered = False
            if channels is not None:
                await channels.wait_started()
                await channels.wait_ready(channel_name)
                await channels.send_outbound(msg)
                delivered = True
            else:
                await bus.publish_outbound(msg)
            _persist_startup_message(
                session_manager,
                natural_key=f"{channel_name}:{chat_id}",
                content=text,
                entrance_style="greeting",
            )
            _log_startup_out(logger, channel_name, chat_id, text, delivered=delivered)
        except Exception as e:
            logger.warning("⚠️ 问候发送失败 / send failed: {}:{} — {}", channel_name, chat_id, e)

    async def _send_external_greetings(
        *, prompt: str, persona_text: str, preferred_language: str
    ) -> None:
        if not targets:
            return
        await asyncio.gather(
            *[
                _send_external_greeting(
                    ch,
                    cid,
                    prompt=prompt,
                    persona_text=persona_text,
                    preferred_language=preferred_language,
                )
                for ch, cid in targets
            ]
        )

    async def _broadcast_onboarding(content: str) -> None:
        for ch, cid in targets:
            try:
                msg = OutboundMessage(channel=ch, chat_id=cid, content=content)
                delivered = False
                if channels is not None:
                    await channels.wait_started()
                    await channels.wait_ready(ch)
                    await channels.send_outbound(msg)
                    delivered = True
                else:
                    await bus.publish_outbound(msg)
                _persist_startup_message(
                    session_manager,
                    natural_key=f"{ch}:{cid}",
                    content=content,
                    entrance_style="assistantReceived",
                )
                _log_startup_out(logger, ch, cid, content, delivered=delivered)
            except Exception as e:
                logger.warning("⚠️ 入门问候失败 / onboarding failed: {}:{} — {}", ch, cid, e)

    async def _send_desktop_greeting(
        *, prompt: str, persona_text: str, preferred_language: str
    ) -> None:
        system_prompt = _build_startup_system_prompt(
            persona_text,
            instructions_text,
            preferred_language,
            channel="desktop",
            chat_id="local",
        )
        text = await _generate_startup_greeting(
            agent,
            logger,
            system_prompt=system_prompt,
            prompt=prompt,
            channel="desktop",
            chat_id="local",
        )
        if text:
            await _emit_desktop_startup_message(
                DesktopStartupMessage(content=text, role="assistant", entrance_style="greeting"),
                "Desktop startup",
            )

    targets = _collect_channel_targets(config, logger)

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
        if on_desktop_startup_message:
            await asyncio.gather(
                _broadcast_onboarding(content),
                _emit_desktop_startup_message(
                    DesktopStartupMessage(
                        content=content,
                        role="assistant",
                        entrance_style="assistantReceived",
                    ),
                    "Onboarding",
                ),
            )
        else:
            await _broadcast_onboarding(content)
        return

    # Ready stage: personalized greeting per channel
    persona_text = _read_persona_text(workspace_path, logger)
    instructions_text = _read_instructions_text(workspace_path, logger)

    persona_lang_tag = _extract_persona_language_tag(persona_text) if persona_text else None
    preferred_language = persona_lang_tag or infer_language(workspace_path)
    prompt = _build_startup_trigger()

    if on_desktop_startup_message:
        await asyncio.gather(
            _send_external_greetings(
                prompt=prompt,
                persona_text=persona_text,
                preferred_language=preferred_language,
            ),
            _send_desktop_greeting(
                prompt=prompt,
                persona_text=persona_text,
                preferred_language=preferred_language,
            ),
        )
    else:
        await _send_external_greetings(
            prompt=prompt,
            persona_text=persona_text,
            preferred_language=preferred_language,
        )


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
