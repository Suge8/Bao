from __future__ import annotations

from collections.abc import Callable, Iterable
from types import SimpleNamespace
from typing import Any

from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.agent.subagent import SpawnRequest, SpawnResult
from bao.session._tree import collect_session_tree_keys

from ._control_types import (
    HubDeleteRequest,
    HubSendRequest,
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
                session_key=normalize_text(request.session_key) or "gateway:direct",
                channel=normalize_channel(request.channel) or "gateway",
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

    async def delete(self, request: HubDeleteRequest) -> bool:
        """删除指定 session（可选包含子 session）"""
        runtime = self._runtime_bundle(request.session_key, request.profile_id)
        session_key = normalize_text(request.session_key)
        if not session_key:
            return False
        session_manager = runtime.session_manager
        deleted_keys = _delete_target_keys(session_manager, session_key, include_children=request.include_children)
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
                origin_channel=normalize_channel(request.origin_channel) or "gateway",
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
        target_keys = _stop_target_keys_for_sessions(getattr(agent, "sessions", None), session_keys)
        if not target_keys:
            return 0
        _clear_interactive_state(agent, target_keys)
        cancelled = _stop_session_runs(getattr(agent, "_session_runs", None), target_keys)
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
        _LocalHubDispatcher(
            session_manager=session_manager,
            agent=_local_runtime_agent(
                session_manager=session_manager,
                agent=agent,
                subagents=subagents,
                session_runs=session_runs,
            ),
            profile_id=profile_id,
            unbind_route=unbind_route,
        )
    )


class _LocalHubDispatcher:
    def __init__(
        self,
        *,
        session_manager: Any | None,
        agent: Any,
        profile_id: str,
        unbind_route: Callable[[str], None] | None,
    ) -> None:
        self._profile_id = normalize_text(profile_id)
        self._runtime = SimpleNamespace(
            profile_id=self._profile_id,
            agent=agent,
            session_manager=session_manager,
        )
        self._unbind_route = unbind_route

    def resolve_profile_id_for(self, explicit_profile_id: object, _session_key: object) -> str:
        return normalize_text(explicit_profile_id) or self._profile_id

    def ensure_runtime(self, _profile_id: object) -> Any:
        return self._runtime

    def unbind_route(self, session_key: object) -> None:
        if not callable(self._unbind_route):
            return
        normalized = normalize_text(session_key)
        if normalized:
            self._unbind_route(normalized)


def _local_runtime_agent(
    *,
    session_manager: Any | None,
    agent: Any | None,
    subagents: Any | None,
    session_runs: Any | None,
) -> Any:
    if agent is not None:
        return agent
    return SimpleNamespace(
        sessions=session_manager,
        _session_runs=session_runs,
        subagents=subagents,
        _clear_interactive_state=lambda _session: False,
    )


def _clear_interactive_state(agent: Any, target_keys: list[str]) -> None:
    sessions = getattr(agent, "sessions", None)
    clear_state = getattr(agent, "_clear_interactive_state", None)
    save_session = getattr(sessions, "save", None)
    if sessions is None or not callable(clear_state) or not callable(save_session):
        return
    get_or_create = getattr(sessions, "get_or_create", None)
    if not callable(get_or_create):
        return
    for key in target_keys:
        session = get_or_create(key)
        if clear_state(session):
            save_session(session)


def _stop_session_runs(session_runs: Any, target_keys: list[str]) -> int:
    if session_runs is None:
        return 0
    stop_session = getattr(session_runs, "stop_session", None)
    if not callable(stop_session):
        return 0
    return sum(int(stop_session(key)) for key in target_keys)


def _stop_target_keys(sessions: Any, session_key: object) -> list[str]:
    key = normalize_text(session_key)
    if not key:
        return []
    target_keys = [key]
    if sessions is None:
        return target_keys
    get_active = getattr(sessions, "get_active_session_key", None)
    if not callable(get_active):
        return target_keys
    active_key = normalize_text(get_active(key))
    if active_key and active_key != key:
        target_keys.append(active_key)
    return target_keys


def _stop_target_keys_for_sessions(sessions: Any, session_keys: Iterable[str]) -> list[str]:
    target_keys: list[str] = []
    seen: set[str] = set()
    for session_key in session_keys:
        for target_key in _stop_target_keys(sessions, session_key):
            if target_key in seen:
                continue
            seen.add(target_key)
            target_keys.append(target_key)
    return target_keys


def _delete_target_keys(session_manager: Any, session_key: str, *, include_children: bool) -> list[str]:
    normalized_key = normalize_text(session_key)
    if not normalized_key:
        return []
    if not include_children:
        return [normalized_key]
    return collect_session_tree_keys(
        normalized_key,
        lambda parent_key: _child_session_keys(session_manager, parent_key),
    )


def _child_session_keys(session_manager: Any, parent_session_key: str) -> tuple[str, ...]:
    list_children = getattr(session_manager, "list_child_sessions", None)
    if not callable(list_children):
        return ()
    child_keys: list[str] = []
    for item in list_children(parent_session_key):
        child_key = normalize_text(item.get("key") if isinstance(item, dict) else "")
        if child_key:
            child_keys.append(child_key)
    return tuple(child_keys)
