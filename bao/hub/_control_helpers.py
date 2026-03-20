from __future__ import annotations

from collections.abc import Callable, Iterable
from types import SimpleNamespace
from typing import Any

from bao.session._tree import collect_session_tree_keys

from ._normalization import normalize_text


class LocalHubDispatcher:
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


def local_runtime_agent(
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


def clear_interactive_state(agent: Any, target_keys: list[str]) -> None:
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


def stop_session_runs(session_runs: Any, target_keys: list[str]) -> int:
    if session_runs is None:
        return 0
    stop_session = getattr(session_runs, "stop_session", None)
    if not callable(stop_session):
        return 0
    return sum(int(stop_session(key)) for key in target_keys)


def stop_target_keys_for_sessions(sessions: Any, session_keys: Iterable[str]) -> list[str]:
    target_keys: list[str] = []
    seen: set[str] = set()
    for session_key in session_keys:
        for target_key in _stop_target_keys(sessions, session_key):
            if target_key in seen:
                continue
            seen.add(target_key)
            target_keys.append(target_key)
    return target_keys


def delete_target_keys(session_manager: Any, session_key: str, *, include_children: bool) -> list[str]:
    normalized_key = normalize_text(session_key)
    if not normalized_key:
        return []
    if not include_children:
        return [normalized_key]
    return collect_session_tree_keys(
        normalized_key,
        lambda parent_key: _child_session_keys(session_manager, parent_key),
    )


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
