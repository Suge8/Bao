from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Callable, Iterable

from loguru import logger

from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.bus.events import ControlEvent, InboundMessage
from bao.hub._channel_binding import ChannelBindingStore
from bao.hub._dispatcher_inputs import (
    dispatch_control_session_key,
    dispatch_session_key,
    normalize_profile_id,
    normalize_profile_ids,
    origin_from_control_event,
    origin_from_message,
    origin_from_request,
)
from bao.hub._dispatcher_models import HubAutomationBundle, HubRuntimeBundle
from bao.hub._dispatcher_runtime import HubDispatcherRuntimeMixin
from bao.hub._route_index import SessionRouteIndex
from bao.hub._route_resolution import HubRouteResolver, SessionOrigin
from bao.hub.directory import HubDirectory
from bao.hub.runtime import HubRuntimePort


class HubDispatcher(HubDispatcherRuntimeMixin):
    """Hub live 调度器：profile 感知的 runtime 路由与唤醒

    负责解析 route、命中 profile/session、lazy 拉起 runtime，
    并调度 inbound/direct/control/automation 请求。
    """

    def __init__(
        self,
        *,
        bus: Any,
        route_index: SessionRouteIndex,
        channel_bindings: ChannelBindingStore,
        runtime_loader: Callable[[str], HubRuntimeBundle],
        automation_loader: Callable[[str], HubAutomationBundle],
        known_profile_ids: Iterable[str],
        default_profile_id: str = "",
    ) -> None:
        self._bus = bus
        self._route_resolver = HubRouteResolver(
            route_index=route_index,
            channel_bindings=channel_bindings,
            default_profile_id=default_profile_id,
        )
        self._runtime_loader = runtime_loader
        self._automation_loader = automation_loader
        self._known_profile_ids = normalize_profile_ids(known_profile_ids)
        self._default_profile_id = normalize_profile_id(default_profile_id)
        self._current_profile_id = self._default_profile_id
        self._runtime_cache: dict[str, HubRuntimeBundle] = {}
        self._automation_cache: dict[str, HubAutomationBundle] = {}
        self._directory_cache: dict[str, HubDirectory] = {}
        self._runtime_port_cache: dict[str, HubRuntimePort] = {}
        self._running = False
        self._run_task: asyncio.Task[Any] | None = None
        self._services_started = False

    @property
    def current_profile_id(self) -> str:
        return self._current_profile_id

    @property
    def agent(self) -> Any:
        runtime = self._current_runtime_bundle()
        return None if runtime is None else runtime.agent

    @property
    def session_manager(self) -> Any:
        runtime = self._current_runtime_bundle()
        return None if runtime is None else runtime.session_manager

    @property
    def directory(self) -> HubDirectory | None:
        runtime = self._current_runtime_bundle()
        return self._directory_for_runtime(runtime)

    def _directory_for_runtime(self, runtime: HubRuntimeBundle | None) -> HubDirectory | None:
        if runtime is None:
            return None
        cached = self._directory_cache.get(runtime.profile_id)
        if cached is None:
            cached = HubDirectory(runtime.session_manager)
            self._directory_cache[runtime.profile_id] = cached
        return cached

    @property
    def runtime_port(self) -> HubRuntimePort | None:
        runtime = self._current_runtime_bundle()
        if runtime is None:
            return None
        cached = self._runtime_port_cache.get(runtime.profile_id)
        if cached is None:
            cached = HubRuntimePort(runtime.session_manager)
            self._runtime_port_cache[runtime.profile_id] = cached
        return cached

    @property
    def cron(self) -> Any:
        automation = self._current_automation_bundle()
        return None if automation is None else automation.cron

    @property
    def heartbeat(self) -> Any:
        automation = self._current_automation_bundle()
        return None if automation is None else automation.heartbeat

    def ensure_runtime(self, profile_id: object) -> HubRuntimeBundle:
        return self._ensure_runtime(profile_id)

    def ensure_automation(self, profile_id: object) -> HubAutomationBundle:
        return self._ensure_automation(profile_id)

    def resolve_profile_id_for(self, explicit_profile_id: object, session_key: object) -> str:
        origin = SessionOrigin.create(channel="hub", chat_id="direct")
        return self._route_resolver.resolve(
            explicit_profile_id=explicit_profile_id,
            session_key=session_key,
            origin=origin,
        ).profile_id

    def unbind_route(self, session_key: object) -> None:
        self._route_resolver.unbind(session_key)

    def set_current_profile(self, profile_id: object) -> bool:
        normalized = self._normalize_target_profile(profile_id)
        if not normalized or normalized == self._current_profile_id:
            return False
        self._current_profile_id = normalized
        self._ensure_automation(normalized)
        return True

    async def start_services(self) -> None:
        if self._services_started:
            return
        self._services_started = True
        for profile_id in self._service_profile_ids():
            automation = self._ensure_automation(profile_id)
            await automation.cron.start()
            await automation.heartbeat.start()

    async def run(self) -> None:
        await self.start_services()
        self._running = True
        self._run_task = asyncio.current_task()
        logger.debug("Hub dispatcher started")
        try:
            while self._running:
                try:
                    item_kind, item = await self._consume_next_bus_item()
                except asyncio.CancelledError:
                    if self._running:
                        raise
                    break
                if item_kind == "control":
                    await self._dispatch_control_event(item)
                    continue
                await self._dispatch_inbound_message(item)
        finally:
            if self._run_task is asyncio.current_task():
                self._run_task = None

    async def process_direct(self, request: ProcessDirectRequest) -> str:
        route = request.to_route_key()
        resolution, runtime = self._resolve_runtime_bundle(
            request_kind="direct",
            explicit_profile_id=route.profile_id,
            session_key=route.session_key,
            origin=origin_from_request(request),
        )
        directory = self._directory_for_runtime(runtime)
        if directory is not None:
            directory.observe_origin(route.session_key or f"{request.channel}:{request.chat_id}", origin_from_request(request))
        self._remember_route(resolution.session_key, resolution.origin, runtime.profile_id)
        resolved_request = replace(request, profile_id=runtime.profile_id)
        return await runtime.agent.process_direct(resolved_request)

    async def close_mcp(self) -> None:
        for runtime in self._runtime_cache.values():
            await runtime.agent.close_mcp()

    async def aclose(self) -> None:
        await self.close_mcp()

    def stop(self) -> None:
        self._running = False
        if self._run_task is not None and not self._run_task.done():
            self._run_task.cancel()
        for runtime in self._runtime_cache.values():
            runtime.agent.stop()
        for automation in self._automation_cache.values():
            automation.heartbeat.stop()
            automation.cron.stop()
        logger.info("👋 停止中枢调度 / hub dispatcher stopping")

    async def _dispatch_inbound_message(self, msg: InboundMessage) -> None:
        session_key = dispatch_session_key(msg)
        resolution, runtime = self._resolve_runtime_bundle(
            request_kind="inbound",
            explicit_profile_id=msg.metadata.get("profile_id"),
            session_key=session_key,
            origin=origin_from_message(msg),
        )
        directory = self._directory_for_runtime(runtime)
        if directory is not None:
            directory.observe_origin(session_key, origin_from_message(msg))
        self._remember_route(session_key, resolution.origin, runtime.profile_id)
        if (msg.content or "").strip().lower() == "/stop":
            await runtime.agent._handle_stop_request(msg)
            return
        await runtime.agent._schedule_message_dispatch(msg, session_key)

    async def _dispatch_control_event(self, event: ControlEvent) -> None:
        session_key = dispatch_control_session_key(event)
        explicit_profile = event.metadata.get("profile_id")
        if not explicit_profile and isinstance(event.payload, dict):
            explicit_profile = event.payload.get("profile_id")
        resolution, runtime = self._resolve_runtime_bundle(
            request_kind="control",
            explicit_profile_id=explicit_profile,
            session_key=session_key,
            origin=origin_from_control_event(event),
        )
        self._remember_route(session_key, resolution.origin, runtime.profile_id)
        runtime.agent._schedule_session_task(
            session_key,
            runtime.agent._dispatch_control(event, dispatch_key=session_key),
        )

    async def _consume_next_bus_item(self) -> tuple[str, InboundMessage | ControlEvent]:
        inbound_task = asyncio.create_task(self._bus.consume_inbound())
        control_task = asyncio.create_task(self._bus.consume_control())
        try:
            done, pending = await asyncio.wait(
                {inbound_task, control_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            for task in (inbound_task, control_task):
                task.cancel()
            await asyncio.gather(inbound_task, control_task, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if inbound_task in done:
            return "inbound", inbound_task.result()
        return "control", control_task.result()
