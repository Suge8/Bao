from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.agent.memory import MemoryPolicy
from bao.bus.events import OutboundMessage
from bao.delivery import DeliveryResult
from bao.hub._builder_automation import (
    CronRunContext,
    build_cron_handler,
    build_heartbeat_service,
)
from bao.hub._builder_types import BuildHubStackOptions, HubStack
from bao.hub._channel_binding import ChannelBindingStore
from bao.hub._dispatcher import (
    HubDispatcher,
)
from bao.hub._dispatcher_models import HubAutomationBundle, HubRuntimeBundle
from bao.hub._observability import record_route_state_prewarm
from bao.hub._route_index import SessionRouteIndex
from bao.profile import (
    ProfileContext,
    ProfileContextOptions,
    ProfileRuntimeMetadataOptions,
    load_profile_registry_snapshot,
    profile_context,
    profile_runtime_metadata,
)

ROUTE_INDEX_FILENAME = "hub-route-index.json"
CHANNEL_BINDINGS_FILENAME = "hub-channel-bindings.json"


@dataclass(frozen=True)
class _HubRuntimeRoots:
    shared_workspace: Path
    prompt_root: Path
    state_root: Path
    cron_store_path: Path


@dataclass(frozen=True)
class _HubBuildContext:
    config: Any
    provider: Any
    logger: Any
    bus: Any
    registry: Any | None
    profile_context: ProfileContext | None
    roots: _HubRuntimeRoots
    session_manager: Any
    cron: Any


def _resolve_runtime_roots(
    shared_workspace: Path,
    profile_context: ProfileContext | None,
) -> _HubRuntimeRoots:
    from bao._profile_runtime import ProfileContextOptions
    from bao._profile_runtime import profile_context as create_profile_context

    # 统一使用 profile 结构，单 profile 模式使用默认 profile
    if profile_context is None:
        profile_context = create_profile_context(
            "default",
            ProfileContextOptions(shared_workspace=shared_workspace),
        )

    return _HubRuntimeRoots(
        shared_workspace=shared_workspace,
        prompt_root=profile_context.prompt_root,
        state_root=profile_context.state_root,
        cron_store_path=profile_context.cron_store_path,
    )


def _resolve_profile_contexts(
    config: Any,
    options: BuildHubStackOptions,
) -> tuple[Path, Any | None, dict[str, ProfileContext | None], str]:
    shared_workspace = Path(str(config.workspace_path)).expanduser()
    current_context = options.profile_context
    if current_context is None:
        return shared_workspace, None, {"": None}, ""
    registry = load_profile_registry_snapshot(shared_workspace)
    contexts: dict[str, ProfileContext | None] = {}
    for spec in registry.profiles:
        contexts[spec.id] = profile_context(
            spec.id,
            ProfileContextOptions(shared_workspace=shared_workspace, registry=registry),
        )
    contexts[current_context.profile_id] = current_context
    return shared_workspace, registry, contexts, current_context.profile_id


def _profile_context_for_id(
    profile_id: str,
    *,
    shared_workspace: Path,
    registry: Any | None,
    contexts: dict[str, ProfileContext | None],
) -> ProfileContext | None:
    normalized = str(profile_id or "").strip()
    if normalized in contexts:
        return contexts[normalized]
    if registry is None or not normalized or registry.get(normalized) is None:
        return None
    resolved = profile_context(
        normalized,
        ProfileContextOptions(shared_workspace=shared_workspace, registry=registry),
    )
    contexts[normalized] = resolved
    return resolved


def _build_profile_metadata(context: _HubBuildContext) -> dict[str, Any] | None:
    profile_context = context.profile_context
    if profile_context is None:
        return None
    return profile_runtime_metadata(
        profile_context.profile_id,
        ProfileRuntimeMetadataOptions(
            shared_workspace=context.roots.shared_workspace,
            display_name=profile_context.display_name,
            registry=context.registry,
        ),
    )


def _build_agent(context: _HubBuildContext) -> Any:
    from bao.agent.loop import AgentLoop

    profile_context = context.profile_context
    defaults = context.config.agents.defaults
    return AgentLoop(
        bus=context.bus,
        provider=context.provider,
        workspace=context.config.workspace_path,
        prompt_root=context.roots.prompt_root,
        state_root=context.roots.state_root,
        profile_id=profile_context.profile_id if profile_context is not None else None,
        profile_metadata=_build_profile_metadata(context),
        model=defaults.model,
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        max_iterations=defaults.max_tool_iterations,
        memory_policy=MemoryPolicy.from_agent_defaults(defaults),
        reasoning_effort=defaults.reasoning_effort,
        service_tier=defaults.service_tier,
        search_config=context.config.tools.web.search,
        web_proxy=context.config.tools.web.proxy,
        exec_config=context.config.tools.exec,
        cron_service=context.cron,
        embedding_config=context.config.tools.embedding,
        restrict_to_workspace=context.config.tools.restrict_to_workspace,
        session_manager=context.session_manager,
        mcp_servers=context.config.tools.mcp_servers,
        available_models=defaults.models,
        config=context.config,
    )


def _session_manager_matches_root(session_manager: Any, expected_root: Path) -> bool:
    workspace = getattr(session_manager, "workspace", None)
    if not isinstance(workspace, (str, Path)):
        return False
    return Path(str(workspace)).expanduser() == expected_root


def build_hub_stack(
    config: Any,
    provider: Any,
    options: BuildHubStackOptions | None = None,
) -> HubStack:
    from loguru import logger

    from bao.bus.queue import MessageBus
    from bao.channels.manager import ChannelManager
    from bao.config.loader import get_data_dir
    from bao.cron.service import CronService
    from bao.session.manager import SessionManager

    resolved_options = options or BuildHubStackOptions()
    bus = MessageBus()
    shared_workspace, registry, profile_contexts, current_profile_id = _resolve_profile_contexts(
        config,
        resolved_options,
    )
    data_dir = get_data_dir()
    route_index = SessionRouteIndex(data_dir / ROUTE_INDEX_FILENAME)
    channel_bindings = ChannelBindingStore(data_dir / CHANNEL_BINDINGS_FILENAME)
    record_route_state_prewarm(route_index=route_index, channel_bindings=channel_bindings)
    runtime_cache: dict[str, HubRuntimeBundle] = {}
    automation_cache: dict[str, HubAutomationBundle] = {}
    dispatcher_ref: dict[str, HubDispatcher] = {}
    channels_ref: dict[str, Any] = {"manager": None}

    async def delivery_sender(msg: OutboundMessage) -> DeliveryResult:
        channels_manager = channels_ref.get("manager")
        if channels_manager is None:
            await bus.publish_outbound(msg)
            return DeliveryResult.queued_result(
                channel=msg.channel,
                chat_id=msg.chat_id,
                detail="channel manager not attached",
            )
        wait_started = getattr(channels_manager, "wait_started", None)
        if callable(wait_started):
            await wait_started()
        wait_ready = getattr(channels_manager, "wait_ready", None)
        if callable(wait_ready):
            await wait_ready(msg.channel)
        direct_send = getattr(channels_manager, "deliver_outbound", None)
        if callable(direct_send):
            result = await direct_send(msg)
            if isinstance(result, DeliveryResult):
                return result
            return DeliveryResult.delivered_result(channel=msg.channel, chat_id=msg.chat_id)
        send_outbound = getattr(channels_manager, "send_outbound", None)
        if callable(send_outbound):
            await send_outbound(msg)
            return DeliveryResult.delivered_result(channel=msg.channel, chat_id=msg.chat_id)
        await bus.publish_outbound(msg)
        return DeliveryResult.queued_result(
            channel=msg.channel,
            chat_id=msg.chat_id,
            detail="channel manager missing delivery path",
        )

    def load_automation(profile_id: str) -> HubAutomationBundle:
        normalized = str(profile_id or "").strip()
        cached = automation_cache.get(normalized)
        if cached is not None:
            return cached
        profile_ctx = _profile_context_for_id(
            normalized,
            shared_workspace=shared_workspace,
            registry=registry,
            contexts=profile_contexts,
        )
        roots = _resolve_runtime_roots(shared_workspace, profile_ctx)
        cron = CronService(roots.cron_store_path)
        context = _HubBuildContext(
            config=config,
            provider=provider,
            logger=logger,
            bus=bus,
            registry=registry,
            profile_context=profile_ctx,
            roots=roots,
            session_manager=None,
            cron=cron,
        )
        resolved_profile_id = profile_ctx.profile_id if profile_ctx is not None else normalized
        dispatcher = dispatcher_ref["dispatcher"]
        cron.on_job = build_cron_handler(
            CronRunContext(
                dispatcher=dispatcher,
                bus=bus,
                logger=logger,
                profile_id=resolved_profile_id,
                delivery_sender=delivery_sender,
            )
        )
        automation = HubAutomationBundle(
            profile_id=resolved_profile_id,
            cron=cron,
            heartbeat=build_heartbeat_service(
                config=config,
                provider=provider,
                logger=logger,
                bus=bus,
                prompt_root=context.roots.prompt_root,
                dispatcher=dispatcher,
                profile_id=resolved_profile_id,
                delivery_sender=delivery_sender,
            ),
        )
        automation_cache[normalized] = automation
        if resolved_profile_id and resolved_profile_id != normalized:
            automation_cache[resolved_profile_id] = automation
        return automation

    def load_runtime(profile_id: str) -> HubRuntimeBundle:
        normalized = str(profile_id or "").strip()
        cached = runtime_cache.get(normalized)
        if cached is not None:
            return cached
        profile_ctx = _profile_context_for_id(
            normalized,
            shared_workspace=shared_workspace,
            registry=registry,
            contexts=profile_contexts,
        )
        roots = _resolve_runtime_roots(shared_workspace, profile_ctx)
        automation = load_automation(normalized)
        session_manager = resolved_options.session_manager
        if session_manager is None or not _session_manager_matches_root(session_manager, roots.state_root):
            session_manager = SessionManager(roots.state_root)
        context = _HubBuildContext(
            config=config,
            provider=provider,
            logger=logger,
            bus=bus,
            registry=registry,
            profile_context=profile_ctx,
            roots=roots,
            session_manager=session_manager,
            cron=automation.cron,
        )
        runtime = HubRuntimeBundle(
            profile_id=profile_ctx.profile_id if profile_ctx is not None else normalized,
            agent=_build_agent(context),
            session_manager=session_manager,
        )
        runtime.agent.set_delivery_sender(delivery_sender)
        runtime_cache[normalized] = runtime
        if runtime.profile_id and runtime.profile_id != normalized:
            runtime_cache[runtime.profile_id] = runtime
        return runtime

    dispatcher = HubDispatcher(
        bus=bus,
        route_index=route_index,
        channel_bindings=channel_bindings,
        runtime_loader=load_runtime,
        automation_loader=load_automation,
        known_profile_ids=tuple(profile_contexts),
        default_profile_id=current_profile_id,
    )
    dispatcher_ref["dispatcher"] = dispatcher
    current_runtime = dispatcher.ensure_runtime(current_profile_id)
    current_automation = dispatcher.ensure_automation(current_profile_id)
    channels = ChannelManager(config, bus, on_channel_error=resolved_options.on_channel_error)
    channels_ref["manager"] = channels
    return HubStack(
        config=config,
        bus=bus,
        session_manager=current_runtime.session_manager,
        cron=current_automation.cron,
        heartbeat=current_automation.heartbeat,
        agent=current_runtime.agent,
        dispatcher=dispatcher,
        channels=channels,
    )


async def shutdown_hub_stack(stack: HubStack, background_tasks: list[Any]) -> None:
    for task in background_tasks:
        task.cancel()
    if stack.dispatcher:
        await stack.dispatcher.close_mcp()
        stack.dispatcher.stop()
    elif stack.agent:
        await stack.agent.close_mcp()
        stack.agent.stop()
    if stack.channels:
        await stack.channels.stop_all()
