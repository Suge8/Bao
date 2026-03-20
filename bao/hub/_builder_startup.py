from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.delivery import DeliveryResult
from bao.hub._builder_delivery import (
    CallbackInvocation,
    StartupDelivery,
    build_startup_activity,
    emit_callback,
    log_startup_out,
    persist_startup_message,
)
from bao.hub._builder_prompt import (
    StartupGreetingRequest,
    StartupPromptOptions,
    _build_startup_fallback_text,
    _build_startup_system_prompt,
    _build_startup_trigger,
    _extract_persona_language_tag,
    _generate_startup_greeting,
    _read_instructions_text,
    _read_persona_text,
)
from bao.hub._builder_targets import _collect_channel_targets
from bao.hub._builder_types import DesktopStartupMessage, StartupGreetingOptions


@dataclass(frozen=True)
class _StartupContext:
    agent: Any
    bus: Any
    logger: Any
    options: StartupGreetingOptions
    targets: tuple[tuple[str, str], ...]
    workspace_path: Path


@dataclass(frozen=True)
class _GreetingPayload:
    prompt: str
    fallback_text: str
    persona_text: str
    instructions_text: str
    preferred_language: str


@dataclass(frozen=True)
class _OnboardingResources:
    lang_picker: str
    persona_greeting: dict[str, str]
    infer_language: Any


def _resolve_workspace_path(options: StartupGreetingOptions) -> Path:
    profile_context = options.profile_context
    if profile_context is not None:
        return profile_context.prompt_root
    return Path(str(options.config.workspace_path)).expanduser()


async def _deliver_message(context: _StartupContext, delivery: StartupDelivery) -> None:
    from bao.bus.events import OutboundMessage

    try:
        outbound = OutboundMessage(
            channel=delivery.channel_name,
            chat_id=delivery.chat_id,
            content=delivery.content,
        )
        result = DeliveryResult.queued_result(
            channel=delivery.channel_name,
            chat_id=delivery.chat_id,
            detail="channels runtime unavailable",
        )
        if context.options.channels is not None:
            await context.options.channels.wait_started()
            await context.options.channels.wait_ready(delivery.channel_name)
            direct_send = getattr(context.options.channels, "deliver_outbound", None)
            if callable(direct_send):
                raw_result = await direct_send(outbound)
                if isinstance(raw_result, DeliveryResult):
                    result = raw_result
                else:
                    result = DeliveryResult.delivered_result(
                        channel=delivery.channel_name,
                        chat_id=delivery.chat_id,
                    )
            else:
                await context.options.channels.send_outbound(outbound)
                result = DeliveryResult.delivered_result(
                    channel=delivery.channel_name,
                    chat_id=delivery.chat_id,
                )
        else:
            await context.bus.publish_outbound(outbound)
        persist_startup_message(context.options.session_manager, delivery)
        log_startup_out(context.logger, delivery, delivered=result.delivered)
    except Exception as exc:
        context.logger.warning(
            "⚠️ 问候发送失败 / send failed: {}:{} — {}",
            delivery.channel_name,
            delivery.chat_id,
            exc,
        )


async def _broadcast_onboarding(context: _StartupContext, content: str) -> None:
    for channel_name, chat_id in context.targets:
        await _deliver_message(
            context,
            StartupDelivery(channel_name, chat_id, content, "assistantReceived"),
        )


async def _send_desktop_greeting(context: _StartupContext, payload: _GreetingPayload) -> None:
    system_prompt = _build_startup_system_prompt(
        StartupPromptOptions(
            persona_text=payload.persona_text,
            instructions_text=payload.instructions_text,
            preferred_language=payload.preferred_language,
            channel="desktop",
            chat_id="local",
        )
    )
    text = await _generate_startup_greeting(
        StartupGreetingRequest(
            agent=context.agent,
            logger=context.logger,
            system_prompt=system_prompt,
            prompt=payload.prompt,
            fallback_text=payload.fallback_text,
            channel="desktop",
            chat_id="local",
        )
    )
    if text:
        await emit_callback(
            CallbackInvocation(
                context.options.on_desktop_startup_message,
                context.logger,
                DesktopStartupMessage(content=text, role="assistant", entrance_style="greeting"),
                "Desktop startup",
            )
        )
        await emit_callback(
            CallbackInvocation(
                context.options.on_startup_activity,
                context.logger,
                {
                    "channelKey": "desktop",
                    "sessionKey": "desktop:local",
                },
                "Desktop startup activity",
            )
        )


def _build_ready_payload(context: _StartupContext, infer_language: Any) -> _GreetingPayload:
    persona_text = _read_persona_text(context.workspace_path, context.logger)
    instructions_text = _read_instructions_text(context.workspace_path, context.logger)
    persona_lang_tag = _extract_persona_language_tag(persona_text) if persona_text else None
    preferred_language = persona_lang_tag or infer_language(context.workspace_path)
    return _GreetingPayload(
        prompt=_build_startup_trigger(),
        fallback_text=_build_startup_fallback_text(preferred_language),
        persona_text=persona_text,
        instructions_text=instructions_text,
        preferred_language=preferred_language,
    )


async def _run_onboarding_stage(
    context: _StartupContext,
    stage: str,
    resources: _OnboardingResources,
) -> None:
    if stage == "lang_select":
        content = resources.lang_picker
    else:
        lang = resources.infer_language(context.workspace_path)
        content = resources.persona_greeting.get(lang, resources.persona_greeting["en"])
    if context.options.on_desktop_startup_message is None:
        await _broadcast_onboarding(context, content)
        return
    await asyncio.gather(
        _broadcast_onboarding(context, content),
        emit_callback(
            CallbackInvocation(
                context.options.on_desktop_startup_message,
                context.logger,
                DesktopStartupMessage(
                    content=content,
                    role="assistant",
                    entrance_style="assistantReceived",
                ),
                "Onboarding",
            )
        ),
    )


async def _run_ready_stage(context: _StartupContext, infer_language: Any) -> None:
    if context.options.on_desktop_startup_message is None:
        return
    await _send_desktop_greeting(context, _build_ready_payload(context, infer_language))


def _activity_targets_for_stage(
    stage: str,
    targets: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if stage in {"lang_select", "persona_setup"}:
        return targets
    return ()


async def send_startup_greeting(
    agent: Any,
    bus: Any,
    options: StartupGreetingOptions,
) -> None:
    from loguru import logger

    from bao.config.onboarding import (
        LANG_PICKER,
        PERSONA_GREETING,
        detect_onboarding_stage,
        infer_language,
    )

    context = _StartupContext(
        agent=agent,
        bus=bus,
        logger=logger,
        options=options,
        targets=tuple(_collect_channel_targets(options.config, logger)),
        workspace_path=_resolve_workspace_path(options),
    )
    stage = detect_onboarding_stage(context.workspace_path)
    await emit_callback(
        CallbackInvocation(
            context.options.on_startup_activity,
            context.logger,
            build_startup_activity(
                _activity_targets_for_stage(stage, context.targets),
                context.options.on_desktop_startup_message is not None,
            ),
            "Startup plan",
        )
    )
    if stage in {"lang_select", "persona_setup"}:
        await _run_onboarding_stage(
            context,
            stage,
            _OnboardingResources(
                lang_picker=LANG_PICKER,
                persona_greeting=PERSONA_GREETING,
                infer_language=infer_language,
            ),
        )
        return
    await _run_ready_stage(context, infer_language)
