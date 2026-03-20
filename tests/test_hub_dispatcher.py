from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.hub._channel_binding import ChannelBindingStore
from bao.hub._dispatcher import HubDispatcher
from bao.hub._dispatcher_models import HubAutomationBundle, HubRuntimeBundle
from bao.hub._route_index import SessionRouteIndex
from bao.runtime_diagnostics import get_runtime_diagnostics_store

pytestmark = pytest.mark.unit


class _FakeRuntimeAgent:
    def __init__(self) -> None:
        self.process_direct = AsyncMock(return_value="ok")
        self.close_mcp = AsyncMock()
        self.stop = AsyncMock()


class _DispatcherHarness:
    def __init__(self, tmp_path) -> None:
        self.tmp_path = tmp_path
        self.route_index = SessionRouteIndex(tmp_path / "routes.json")
        self.channel_bindings = ChannelBindingStore(tmp_path / "channel-bindings.json")
        self.runtimes: dict[str, HubRuntimeBundle] = {}
        self.services: dict[str, HubAutomationBundle] = {}

    def create_dispatcher(self) -> HubDispatcher:
        return HubDispatcher(
            bus=SimpleNamespace(),
            route_index=self.route_index,
            channel_bindings=self.channel_bindings,
            runtime_loader=self.load_runtime,
            automation_loader=self.load_automation,
            known_profile_ids=("default", "work"),
            default_profile_id="default",
        )

    def load_runtime(self, profile_id: str) -> HubRuntimeBundle:
        normalized = str(profile_id or "").strip()
        runtime = self.runtimes.get(normalized)
        if runtime is not None:
            return runtime
        agent = _FakeRuntimeAgent()
        runtime = HubRuntimeBundle(
            profile_id=normalized,
            agent=agent,
            session_manager=SimpleNamespace(workspace=self.tmp_path / normalized),
        )
        self.runtimes[normalized] = runtime
        return runtime

    def load_automation(self, profile_id: str) -> HubAutomationBundle:
        normalized = str(profile_id or "").strip()
        cached = self.services.get(normalized)
        if cached is not None:
            return cached
        cached = HubAutomationBundle(
            profile_id=normalized,
            cron=SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), status=lambda: {"jobs": 0}),
            heartbeat=SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), interval_s=1800),
        )
        self.services[normalized] = cached
        return cached


def test_process_direct_reuses_route_index_for_follow_up_messages(tmp_path) -> None:
    get_runtime_diagnostics_store().clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        session_key="desktop:local::s1",
        channel="desktop",
        chat_id="local",
        profile_id="work",
    )))
    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="follow up",
        session_key="desktop:local::s1",
        channel="desktop",
        chat_id="local",
    )))

    work_agent = harness.runtimes["work"].agent
    assert work_agent.process_direct.await_count == 2
    first_request = work_agent.process_direct.await_args_list[0].args[0]
    second_request = work_agent.process_direct.await_args_list[1].args[0]
    assert first_request.profile_id == "work"
    assert second_request.profile_id == "work"
    assert harness.route_index.resolve("desktop:local::s1") == "work"


def test_route_miss_uses_default_profile_instead_of_current_profile(tmp_path) -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    assert dispatcher.set_current_profile("work") is True

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        channel="desktop",
        chat_id="fresh",
    )))

    default_agent = harness.runtimes["default"].agent
    assert default_agent.process_direct.await_count == 1
    assert "work" not in harness.runtimes or harness.runtimes["work"].agent.process_direct.await_count == 0
    snapshot = store.snapshot(max_events=4, max_log_lines=0, allowed_sources=("hub_dispatch",))
    assert snapshot["recent_events"][0]["code"] == "hub_route_observed"
    assert snapshot["recent_events"][0]["level"] == "warning"
    assert snapshot["recent_events"][0]["details"]["source"] == "default_profile"
    assert snapshot["recent_events"][0]["details"]["reason"] == "registry_default_profile"
    assert snapshot["recent_events"][0]["details"]["runtime_cached"] is False


def test_process_direct_reuses_channel_binding_when_session_key_changes(tmp_path) -> None:
    get_runtime_diagnostics_store().clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        session_key="telegram:-100123:topic:42",
        channel="telegram",
        chat_id="-100123",
        profile_id="work",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )))
    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="follow up",
        session_key="telegram:-100123:topic:42:transient",
        channel="telegram",
        chat_id="-100123",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )))

    work_agent = harness.runtimes["work"].agent
    assert work_agent.process_direct.await_count == 2
    second_request = work_agent.process_direct.await_args_list[1].args[0]
    assert second_request.profile_id == "work"


def test_channel_binding_keeps_thread_dimension_isolated(tmp_path) -> None:
    get_runtime_diagnostics_store().clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        session_key="telegram:-100123:topic:42",
        channel="telegram",
        chat_id="-100123",
        profile_id="work",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )))
    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="fresh thread",
        session_key="telegram:-100123:topic:99",
        channel="telegram",
        chat_id="-100123",
        metadata={"bot_id": "bot-1", "message_thread_id": 99},
    )))

    default_agent = harness.runtimes["default"].agent
    work_agent = harness.runtimes["work"].agent
    assert work_agent.process_direct.await_count == 1
    assert default_agent.process_direct.await_count == 1


def test_cold_start_observation_records_route_and_runtime_timings(tmp_path) -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        session_key="desktop:local::s1",
        channel="desktop",
        chat_id="local",
        profile_id="work",
    )))
    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="follow up",
        session_key="desktop:local::s1",
        channel="desktop",
        chat_id="local",
        profile_id="work",
    )))

    snapshot = store.snapshot(max_events=8, max_log_lines=0, allowed_sources=("hub_dispatch",))
    observed = [
        event
        for event in snapshot["recent_events"]
        if event.get("code") == "hub_route_observed"
    ]

    assert len(observed) == 1
    details = observed[0]["details"]
    assert details["request_kind"] == "direct"
    assert details["runtime_cached"] is False
    assert details["source"] == "explicit"
    assert details["reason"] == "explicit_profile_id"
    assert details["route_resolve_ms"] >= 0
    assert details["runtime_load_ms"] >= 0


def test_process_direct_observes_session_directory_binding(tmp_path) -> None:
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    asyncio_run(dispatcher.process_direct(ProcessDirectRequest(
        content="hello",
        session_key="telegram:-100123:topic:42::main",
        channel="telegram",
        chat_id="-100123",
        profile_id="work",
        metadata={"bot_id": "bot-1", "message_thread_id": 42},
    )))

    directory = dispatcher._directory_cache.get("work")
    assert directory is not None
    record = directory.get_session_directory_record("telegram:-100123:topic:42::main")
    assert record is not None
    assert record["account_id"] == "bot-1"
    assert record["thread_id"] == "42"
    assert record["availability"] == "active"


@pytest.mark.asyncio
async def test_start_services_initializes_all_known_profile_automations(tmp_path) -> None:
    get_runtime_diagnostics_store().clear()
    harness = _DispatcherHarness(tmp_path)
    dispatcher = harness.create_dispatcher()

    await dispatcher.start_services()

    assert set(harness.services) == {"default", "work"}
    for bundle in harness.services.values():
        bundle.cron.start.assert_awaited_once()
        bundle.heartbeat.start.assert_awaited_once()


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
