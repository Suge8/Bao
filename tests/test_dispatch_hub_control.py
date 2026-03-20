from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bao.agent.subagent import SpawnResult
from bao.hub import (
    HubClearActiveSessionRequest,
    HubControl,
    HubCreateSessionRequest,
    HubDeleteRequest,
    HubSendRequest,
    HubSetActiveSessionRequest,
    HubSpawnChildRequest,
    HubStopRequest,
    local_hub_control,
)
from bao.hub._route_index import SessionRouteIndex

pytestmark = pytest.mark.unit


class _FakeSessions:
    def __init__(self, *, active_key: str = "") -> None:
        self._active_key = active_key
        self.saved: list[str] = []

    def get_active_session_key(self, _key: str) -> str:
        return self._active_key

    def get_or_create(self, key: str) -> SimpleNamespace:
        return SimpleNamespace(key=key, metadata={"_pending_model_select": True})

    def save(self, session: SimpleNamespace) -> None:
        self.saved.append(session.key)


class _FakeSessionRuns:
    def __init__(self) -> None:
        self.stopped: list[str] = []

    def stop_session(self, key: str) -> int:
        self.stopped.append(key)
        return 1


class _FakeSessionManager:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.created: list[str] = []
        self.active_updates: list[tuple[str, str]] = []
        self.cleared_natural_keys: list[str] = []

    def list_child_sessions(self, key: str) -> list[dict[str, str]]:
        if key == "desktop:local::parent":
            return [{"key": "subagent:desktop:local::parent::t1"}]
        if key == "subagent:desktop:local::parent::t1":
            return [{"key": "subagent:subagent:desktop:local::parent::t1::g1"}]
        return []

    def get_or_create(self, key: str) -> SimpleNamespace:
        self.created.append(key)
        return SimpleNamespace(key=key, metadata={})

    def save(self, session: SimpleNamespace) -> None:
        self.created.append(f"saved:{session.key}")

    def set_active_session_key(self, natural_key: str, session_key: str) -> None:
        self.active_updates.append((natural_key, session_key))

    def clear_active_session_key(self, natural_key: str) -> None:
        self.cleared_natural_keys.append(natural_key)

    def delete_session_tree(self, key: str) -> bool:
        self.deleted.append(key)
        return True


class _FakeDispatcher:
    def __init__(self, *, active_key: str = "desktop:local::active") -> None:
        self.process_direct = AsyncMock(return_value="ok")
        self.subagents = SimpleNamespace(
            cancel_by_session=AsyncMock(return_value=2),
            spawn=AsyncMock(return_value=SpawnResult.spawned(task_id="t1", label="child", child_session_key="child")),
        )
        self.sessions = _FakeSessions(active_key=active_key)
        self.session_runs = _FakeSessionRuns()
        self.session_manager = _FakeSessionManager()
        self.agent = SimpleNamespace(
            sessions=self.sessions,
            _session_runs=self.session_runs,
            subagents=self.subagents,
            _clear_interactive_state=lambda session: bool(session.metadata),
        )
        self.runtime = SimpleNamespace(agent=self.agent, session_manager=self.session_manager)
        self.ensure_runtime_calls: list[str] = []
        self.unbound_keys: list[str] = []

    def resolve_profile_id_for(self, explicit_profile_id: object, _session_key: object) -> str:
        return str(explicit_profile_id or "default").strip() or "default"

    def ensure_runtime(self, profile_id: str) -> SimpleNamespace:
        self.ensure_runtime_calls.append(profile_id)
        return self.runtime

    def unbind_route(self, key: str) -> None:
        self.unbound_keys.append(key)


class _DispatcherWithoutUnbind(_FakeDispatcher):
    def __init__(self, tmp_path) -> None:
        super().__init__(active_key="")
        self._route_index = SessionRouteIndex(tmp_path / "routes.json")
        self._route_index.bind("desktop:local::parent", "default")
        self._route_index.bind("subagent:desktop:local::parent::t1", "default")
        self._route_index.bind("subagent:subagent:desktop:local::parent::t1::g1", "default")

    unbind_route = None


@pytest.mark.asyncio
async def test_hub_control_send_delegates_to_dispatcher() -> None:
    dispatcher = _FakeDispatcher()

    result = await HubControl(dispatcher).send(
        HubSendRequest(
            content="hello",
            session_key=" desktop:local::s1 ",
            channel=" Desktop ",
            chat_id=" local ",
            profile_id=" work ",
            metadata={"source": "desktop"},
        )
    )

    assert result == "ok"
    request = dispatcher.process_direct.await_args.args[0]
    assert request.session_key == "desktop:local::s1"
    assert request.channel == "desktop"
    assert request.chat_id == "local"
    assert request.profile_id == "work"
    assert request.metadata == {"source": "desktop"}


@pytest.mark.asyncio
async def test_hub_control_stop_clears_state_and_cancels_runtime() -> None:
    dispatcher = _FakeDispatcher()

    cancelled = await HubControl(dispatcher).stop(HubStopRequest(session_key="desktop:local"))

    assert cancelled == 6
    assert dispatcher.ensure_runtime_calls == ["default"]
    assert dispatcher.session_runs.stopped == ["desktop:local", "desktop:local::active"]
    assert dispatcher.sessions.saved == ["desktop:local", "desktop:local::active"]
    assert dispatcher.subagents.cancel_by_session.await_args_list[0].args[0] == "desktop:local"
    assert dispatcher.subagents.cancel_by_session.await_args_list[1].args[0] == "desktop:local::active"


@pytest.mark.asyncio
async def test_hub_control_create_session_persists_then_optionally_activates() -> None:
    dispatcher = _FakeDispatcher(active_key="")

    created = await HubControl(dispatcher).create_session(
        HubCreateSessionRequest(
            natural_key="desktop:local",
            session_key="desktop:local::s1",
            activate=True,
        )
    )

    assert created == "desktop:local::s1"
    assert dispatcher.session_manager.created == ["desktop:local::s1", "saved:desktop:local::s1"]
    assert dispatcher.session_manager.active_updates == [("desktop:local", "desktop:local::s1")]


@pytest.mark.asyncio
async def test_hub_control_set_and_clear_active_session_delegate_to_session_manager() -> None:
    dispatcher = _FakeDispatcher(active_key="")
    control = HubControl(dispatcher)

    updated = await control.set_active_session(
        HubSetActiveSessionRequest(
            natural_key="desktop:local",
            session_key="desktop:local::s2",
        )
    )
    await control.clear_active_session(HubClearActiveSessionRequest(natural_key="desktop:local"))

    assert updated == "desktop:local::s2"
    assert dispatcher.session_manager.active_updates == [("desktop:local", "desktop:local::s2")]
    assert dispatcher.session_manager.cleared_natural_keys == ["desktop:local"]


@pytest.mark.asyncio
async def test_hub_control_delete_stops_then_unbinds_deleted_tree() -> None:
    dispatcher = _FakeDispatcher(active_key="")

    deleted = await HubControl(dispatcher).delete(
        HubDeleteRequest(session_key="desktop:local::parent", include_children=True)
    )

    assert deleted is True
    assert dispatcher.session_manager.deleted == ["desktop:local::parent"]
    assert dispatcher.session_runs.stopped == [
        "desktop:local::parent",
        "subagent:desktop:local::parent::t1",
        "subagent:subagent:desktop:local::parent::t1::g1",
    ]
    assert [call.args[0] for call in dispatcher.subagents.cancel_by_session.await_args_list] == [
        "desktop:local::parent",
        "subagent:desktop:local::parent::t1",
        "subagent:subagent:desktop:local::parent::t1::g1",
    ]
    assert dispatcher.unbound_keys == [
        "desktop:local::parent",
        "subagent:desktop:local::parent::t1",
        "subagent:subagent:desktop:local::parent::t1::g1",
    ]


@pytest.mark.asyncio
async def test_hub_control_delete_falls_back_to_route_index_unbind(tmp_path) -> None:
    dispatcher = _DispatcherWithoutUnbind(tmp_path)

    deleted = await HubControl(dispatcher).delete(
        HubDeleteRequest(session_key="desktop:local::parent", include_children=True)
    )

    assert deleted is True
    assert dispatcher._route_index.resolve("desktop:local::parent") == ""
    assert dispatcher._route_index.resolve("subagent:desktop:local::parent::t1") == ""
    assert dispatcher._route_index.resolve("subagent:subagent:desktop:local::parent::t1::g1") == ""


@pytest.mark.asyncio
async def test_hub_control_spawn_child_uses_subagent_manager() -> None:
    dispatcher = _FakeDispatcher()

    result = await HubControl(dispatcher).spawn_child(
        HubSpawnChildRequest(
            task="research",
            label="child",
            session_key="desktop:local::parent",
            profile_id="work",
            origin_channel=" desktop ",
            origin_chat_id=" local ",
            child_session_key="subagent:desktop:local::parent::child",
        )
    )

    assert result.status == "spawned"
    request = dispatcher.subagents.spawn.await_args.args[0]
    assert request.task == "research"
    assert request.label == "child"
    assert request.session_key == "desktop:local::parent"
    assert request.origin_channel == "desktop"
    assert request.origin_chat_id == "local"
    assert request.child_session_key == "subagent:desktop:local::parent::child"


@pytest.mark.asyncio
async def test_local_hub_control_spawn_child_uses_local_subagent_manager() -> None:
    subagents = SimpleNamespace(
        spawn=AsyncMock(
            return_value=SpawnResult.spawned(
                task_id="t1",
                label="child",
                child_session_key="subagent:desktop:local::parent::child",
            )
        )
    )

    result = await local_hub_control(subagents=subagents).spawn_child(
        HubSpawnChildRequest(
            task="research",
            session_key="desktop:local::parent",
            origin_channel="desktop",
            origin_chat_id="local",
            child_session_key="subagent:desktop:local::parent::child",
        )
    )

    assert result.status == "spawned"
    request = subagents.spawn.await_args.args[0]
    assert request.task == "research"
    assert request.session_key == "desktop:local::parent"
    assert request.child_session_key == "subagent:desktop:local::parent::child"
