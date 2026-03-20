from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.agent.subagent import SpawnRequest, SpawnResult

from ._control_helpers import (
    LocalHubDispatcher,
    clear_interactive_state,
    delete_target_keys,
    local_runtime_agent,
    stop_session_runs,
    stop_target_keys_for_sessions,
)
from ._control_types import (
    HubClearActiveSessionRequest,
    HubCreateSessionRequest,
    HubDeleteRequest,
    HubSendRequest,
    HubSetActiveSessionRequest,
    HubSpawnChildRequest,
    HubStopRequest,
)
from ._exceptions import HubDispatcherMissingError, HubRuntimeNotReadyError
from ._normalization import normalize_channel, normalize_media, normalize_text


class HubControl:
    """Hub 统一控制面：session 控制动作的唯一入口

    提供 send/stop/delete/spawn_child 等显式控制动作，
    是所有 session 生命周期管理的统一 facade。
    """

    def __init__(self, dispatcher: Any) -> None:
        self._dispatcher = dispatcher

    async def send(self, request: HubSendRequest) -> str:
        """发送消息到指定 session"""
        return await self._dispatcher.process_direct(
            ProcessDirectRequest(
                content=request.content,
                session_key=normalize_text(request.session_key) or "hub:direct",
                channel=normalize_channel(request.channel) or "hub",
                chat_id=normalize_text(request.chat_id) or "direct",
                profile_id=normalize_text(request.profile_id) or None,
                reply_target_id=request.reply_target_id,
                media=normalize_media(request.media),
                on_progress=request.on_progress,
                on_event=request.on_event,
                ephemeral=bool(request.ephemeral),
                metadata=dict(request.metadata),
            )
        )

    async def stop(self, request: HubStopRequest) -> int:
        """停止指定 session 的运行"""
        runtime = self._runtime_bundle(request.session_key, request.profile_id)
        return await self._stop_runtime_sessions(runtime.agent, [normalize_text(request.session_key)])

    async def create_session(self, request: HubCreateSessionRequest) -> str:
        runtime = self._runtime_bundle(request.session_key or request.natural_key, request.profile_id)
        session_manager = getattr(runtime, "session_manager", None)
        if session_manager is None:
            raise HubRuntimeNotReadyError("Session manager not initialized")
        session_key = normalize_text(request.session_key)
        natural_key = normalize_text(request.natural_key)
        if not session_key or not natural_key:
            raise HubRuntimeNotReadyError("natural_key and session_key are required")
        session = session_manager.get_or_create(session_key)
        session_manager.save(session)
        if request.activate:
            session_manager.set_active_session_key(natural_key, session_key)
        return session_key

    async def set_active_session(self, request: HubSetActiveSessionRequest) -> str:
        runtime = self._runtime_bundle(request.session_key or request.natural_key, request.profile_id)
        session_manager = getattr(runtime, "session_manager", None)
        if session_manager is None:
            raise HubRuntimeNotReadyError("Session manager not initialized")
        session_key = normalize_text(request.session_key)
        natural_key = normalize_text(request.natural_key)
        if not session_key or not natural_key:
            raise HubRuntimeNotReadyError("natural_key and session_key are required")
        session_manager.set_active_session_key(natural_key, session_key)
        return session_key

    async def clear_active_session(self, request: HubClearActiveSessionRequest) -> None:
        runtime = self._runtime_bundle(request.natural_key, request.profile_id)
        session_manager = getattr(runtime, "session_manager", None)
        if session_manager is None:
            raise HubRuntimeNotReadyError("Session manager not initialized")
        natural_key = normalize_text(request.natural_key)
        if not natural_key:
            raise HubRuntimeNotReadyError("natural_key is required")
        session_manager.clear_active_session_key(natural_key)

    async def delete(self, request: HubDeleteRequest) -> bool:
        """删除指定 session（可选包含子 session）"""
        runtime = self._runtime_bundle(request.session_key, request.profile_id)
        session_key = normalize_text(request.session_key)
        if not session_key:
            return False
        session_manager = runtime.session_manager
        deleted_keys = delete_target_keys(session_manager, session_key, include_children=request.include_children)
        await self._stop_runtime_sessions(runtime.agent, deleted_keys)

        delete_name = "delete_session_tree" if request.include_children else "delete_session"
        delete_fn = getattr(session_manager, delete_name, None)
        if not callable(delete_fn):
            raise HubRuntimeNotReadyError(f"Session manager missing {delete_name}")
        deleted = bool(delete_fn(session_key))
        if deleted:
            self._unbind_routes(deleted_keys)
        return deleted

    async def spawn_child(self, request: HubSpawnChildRequest) -> SpawnResult:
        """生成子 session（subagent）"""
        runtime = self._runtime_bundle(request.session_key, request.profile_id)
        subagents = getattr(runtime.agent, "subagents", None)
        if subagents is None:
            raise HubRuntimeNotReadyError("Subagent manager not initialized")
        return await subagents.spawn(
            SpawnRequest(
                task=request.task,
                label=request.label,
                origin_channel=normalize_channel(request.origin_channel) or "hub",
                origin_chat_id=normalize_text(request.origin_chat_id) or "direct",
                session_key=normalize_text(request.session_key) or None,
                context_from=normalize_text(request.context_from) or None,
                child_session_key=normalize_text(request.child_session_key) or None,
            )
        )

    def _runtime_bundle(self, session_key: object, profile_id: object) -> Any:
        resolve_profile = getattr(self._dispatcher, "resolve_profile_id_for", None) or getattr(
            self._dispatcher, "_resolve_profile_id", None
        )
        if not callable(resolve_profile):
            raise HubDispatcherMissingError("Dispatcher missing profile resolver")
        ensure_runtime = getattr(self._dispatcher, "ensure_runtime", None)
        if not callable(ensure_runtime):
            raise HubDispatcherMissingError("Dispatcher missing runtime loader")
        resolved_profile_id = resolve_profile(profile_id, session_key)
        return ensure_runtime(resolved_profile_id)

    async def _stop_runtime_sessions(self, agent: Any, session_keys: Iterable[str]) -> int:
        target_keys = stop_target_keys_for_sessions(getattr(agent, "sessions", None), session_keys)
        if not target_keys:
            return 0
        clear_interactive_state(agent, target_keys)
        cancelled = stop_session_runs(getattr(agent, "_session_runs", None), target_keys)
        subagents = getattr(agent, "subagents", None)
        if subagents is None:
            return cancelled
        cancel_by_session = getattr(subagents, "cancel_by_session", None)
        if not callable(cancel_by_session):
            return cancelled
        sub_cancelled = 0
        for key in target_keys:
            sub_cancelled += int(await cancel_by_session(key, wait=False))
        return cancelled + sub_cancelled

    def _unbind_routes(self, session_keys: list[str]) -> None:
        unbind_fn = getattr(self._dispatcher, "unbind_route", None)
        if not callable(unbind_fn):
            route_index = getattr(self._dispatcher, "_route_index", None)
            if route_index is not None:
                unbind_fn = getattr(route_index, "unbind", None)
        if callable(unbind_fn):
            for key in session_keys:
                unbind_fn(key)


def local_hub_control(
    *,
    session_manager: Any | None = None,
    agent: Any | None = None,
    subagents: Any | None = None,
    session_runs: Any | None = None,
    profile_id: str = "",
    unbind_route: Callable[[str], None] | None = None,
) -> HubControl:
    return HubControl(
        LocalHubDispatcher(
            session_manager=session_manager,
            agent=local_runtime_agent(
                session_manager=session_manager,
                agent=agent,
                subagents=subagents,
                session_runs=session_runs,
            ),
            profile_id=profile_id,
            unbind_route=unbind_route,
        )
    )
