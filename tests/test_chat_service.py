"""Tests for ChatService state machine and message queue."""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar, cast
from unittest.mock import MagicMock, patch

from bao.gateway.builder import DesktopStartupMessage
from bao.session.manager import SessionChangeEvent

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QGuiApplication = QtGui.QGuiApplication
_T = TypeVar("_T")


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


_LIVE_CHAT_SERVICES = []


@pytest.fixture(autouse=True)
def cleanup_chat_services(qt_app):
    yield
    while _LIVE_CHAT_SERVICES:
        svc = _LIVE_CHAT_SERVICES.pop()
        try:
            svc._history_sync_timer.stop()
        except Exception:
            pass
        try:
            svc.deleteLater()
        except Exception:
            pass
    qt_app.processEvents()


def make_service():
    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import ChatService

    model = ChatMessageModel()

    def _submit_and_close(coro: Coroutine[Any, Any, _T]) -> concurrent.futures.Future[_T]:
        try:
            coro.close()
        except Exception:
            pass
        fut: concurrent.futures.Future[_T] = concurrent.futures.Future()
        fut.set_result(cast(_T, None))
        return fut

    runner = MagicMock()
    runner.submit = MagicMock(side_effect=_submit_and_close)
    svc = ChatService(model, runner)
    _LIVE_CHAT_SERVICES.append(svc)
    return svc, model


class _SessionManagerWithListeners:
    def __init__(self) -> None:
        self.listeners: list[Any] = []

    def add_change_listener(self, listener: Any) -> None:
        self.listeners.append(listener)

    def remove_change_listener(self, listener: Any) -> None:
        if listener in self.listeners:
            self.listeners.remove(listener)

    def emit(self, session_key: str, kind: str) -> None:
        event = SessionChangeEvent(session_key=session_key, kind=kind)
        for listener in list(self.listeners):
            listener(event)


def test_initial_state():
    svc, _ = make_service()
    assert svc.state == "idle"
    assert svc.lastError == ""


def test_send_message_appends_user_row():
    svc, model = make_service()
    svc.sendMessage("hello")
    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "user"
    assert model._messages[0]["content"] == "hello"


def test_send_empty_message_ignored():
    svc, model = make_service()
    svc.sendMessage("   ")
    assert model.rowCount() == 0


def test_send_message_emits_signal():
    svc, model = make_service()
    emitted = []
    svc.messageAppended.connect(emitted.append)
    svc.sendMessage("test")
    assert len(emitted) == 1
    assert emitted[0] == 0  # row 0


def test_stop_from_idle_is_noop():
    svc, _ = make_service()
    svc.stop()  # should not raise
    assert svc.state == "stopped"


def test_state_transitions_to_starting_on_start():
    svc, _ = make_service()
    states = []
    svc.stateChanged.connect(states.append)

    with patch.object(svc, "_init_gateway", return_value=None):
        svc.start()

    assert "starting" in states


def test_init_gateway_keeps_subagent_system_callback_unbound():
    from types import SimpleNamespace

    svc, _model = make_service()

    fake_agent = SimpleNamespace(on_system_response=None)

    async def _noop(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    fake_agent.run = _noop
    fake_channels = SimpleNamespace(enabled_channels=["desktop"], start_all=_noop)
    fake_cron = SimpleNamespace(start=_noop, status=lambda: {"jobs": 0})
    fake_heartbeat = SimpleNamespace(start=_noop)
    fake_stack = SimpleNamespace(
        agent=fake_agent,
        channels=fake_channels,
        cron=fake_cron,
        heartbeat=fake_heartbeat,
        session_manager=MagicMock(),
        bus=MagicMock(),
        config=SimpleNamespace(),
    )
    fake_config = SimpleNamespace(workspace_path="/tmp/bao-test")

    with (
        patch("bao.config.loader.ensure_first_run"),
        patch("bao.config.loader.get_config_path", return_value="/tmp/config.jsonc"),
        patch("bao.config.loader.load_config", return_value=fake_config),
        patch("bao.providers.make_provider", return_value=MagicMock()),
        patch("bao.gateway.builder.build_gateway_stack", return_value=fake_stack),
        patch("bao.gateway.builder.send_startup_greeting", new=_noop),
    ):
        asyncio.run(svc._init_gateway())

    assert fake_agent.on_system_response is None


def test_init_gateway_uses_injected_config_snapshot() -> None:
    from types import SimpleNamespace

    svc, _model = make_service()
    svc.setConfigData({"agents": {"defaults": {"model": "openai/gpt-4o"}}, "providers": {}})

    async def _noop(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        return None

    fake_stack = SimpleNamespace(
        agent=SimpleNamespace(run=_noop, on_system_response=None),
        channels=SimpleNamespace(enabled_channels=["desktop"], start_all=_noop),
        cron=SimpleNamespace(start=_noop, status=lambda: {"jobs": 0}),
        heartbeat=SimpleNamespace(start=_noop),
        session_manager=MagicMock(),
        bus=MagicMock(),
        config=SimpleNamespace(),
    )
    fake_config = SimpleNamespace(
        workspace_path="/tmp/bao-test",
        agents=SimpleNamespace(defaults=SimpleNamespace(model="openai/gpt-4o")),
    )

    with (
        patch("bao.config.loader.ensure_first_run"),
        patch("bao.config.loader.get_config_path", return_value="/tmp/config.jsonc"),
        patch(
            "bao.config.loader.load_config", side_effect=AssertionError("should not reload config")
        ),
        patch("bao.config.schema.Config.model_validate", return_value=fake_config),
        patch("bao.providers.make_provider", return_value=MagicMock()),
        patch("bao.gateway.builder.build_gateway_stack", return_value=fake_stack),
        patch("bao.gateway.builder.send_startup_greeting", new=_noop),
    ):
        asyncio.run(svc._init_gateway())


def test_init_gateway_surfaces_config_path_when_loader_exits() -> None:
    svc, _model = make_service()

    with (
        patch("bao.config.loader.ensure_first_run"),
        patch("bao.config.loader.get_config_path", return_value="/tmp/config.jsonc"),
        patch("bao.config.loader.load_config", side_effect=SystemExit(0)),
    ):
        with pytest.raises(RuntimeError, match="/tmp/config.jsonc"):
            asyncio.run(svc._init_gateway())


def test_stop_invalidates_inflight_init_result() -> None:
    svc, _model = make_service()

    with patch.object(svc, "_init_gateway", return_value=None):
        svc.start()

    request_id = svc._lifecycle_request_id - 1
    svc.stop()
    svc._handle_init_result(request_id, True, "", MagicMock(), ["telegram"])

    assert svc.state == "stopped"
    assert svc.property("gatewayDetail") == ""


def test_double_start_is_noop():
    svc, _ = make_service()
    states = []
    svc.stateChanged.connect(states.append)

    with patch.object(svc, "_init_gateway", return_value=None):
        svc.start()
        svc.start()  # second call should be ignored

    assert states.count("starting") == 1


def test_set_error_changes_state():
    svc, _ = make_service()
    errors = []
    states = []
    svc.errorChanged.connect(errors.append)
    svc.stateChanged.connect(states.append)
    svc._set_error("boom")
    assert svc.state == "error"
    assert svc.lastError == "boom"
    assert svc.property("gatewayDetail") == "boom"
    assert svc.property("gatewayDetailIsError") is True
    assert "boom" in errors
    assert "error" in states


def test_set_error_does_not_append_chat_message():
    svc, model = make_service()

    svc._set_error("boom")

    assert model.rowCount() == 0


def test_configured_gateway_channels_project_idle_channels() -> None:
    svc, _model = make_service()

    svc.setConfiguredGatewayChannels(["imessage", "telegram", "imessage"])

    channels = svc.property("gatewayChannels")
    assert [item["channel"] for item in channels] == ["telegram", "imessage"]
    assert all(item["state"] == "idle" for item in channels)


def test_gateway_channels_mark_only_failed_channel_as_error() -> None:
    svc, _model = make_service()
    session_manager = MagicMock()
    svc.setConfiguredGatewayChannels(["telegram", "imessage"])
    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])
    svc._handle_channel_error("start_failed", "telegram", "bad token")

    channels = {item["channel"]: item for item in svc.property("gatewayChannels")}
    assert channels["telegram"]["state"] == "error"
    assert channels["telegram"]["detail"] == "bad token"
    assert channels["imessage"]["state"] == "running"


def test_show_system_response_immediate():
    """System response should appear immediately when not processing."""
    svc, model = make_service()
    svc._show_system_response("Task done")
    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "system"
    assert model._messages[0]["content"] == "Task done"
    assert model._messages[0]["status"] == "done"
    assert model._messages[0]["entrancestyle"] == "system"


def test_system_response_queued_while_processing():
    """System response should be queued when main streaming is active."""
    svc, model = make_service()
    svc._processing = True
    svc._handle_system_response("Queued msg")
    assert model.rowCount() == 0  # not displayed yet
    assert len(svc._pending_notifications) == 1
    queued = svc._pending_notifications[0]
    assert queued.role == "system"
    assert queued.content == "Queued msg"
    assert queued.session_key == "desktop:local"
    assert queued.entrance_style == "system"


def test_system_response_drained_after_send():
    """Pending system responses should drain after send completes."""
    svc, model = make_service()
    svc._processing = True
    svc._handle_system_response("Deferred")
    row = model.append_assistant("reply", status="typing")
    svc._handle_send_result(row, True, "reply")
    assert model._messages[0]["status"] == "done"
    # Deferred system response should now be displayed
    assert model.rowCount() == 2
    assert model._messages[1]["role"] == "system"
    assert model._messages[1]["content"] == "Deferred"


def test_system_response_for_other_session_persisted_but_not_shown():
    svc, model = make_service()
    svc._session_key = "desktop:active"
    session = MagicMock()
    sm = MagicMock()
    sm.get_or_create.return_value = session
    svc._session_manager = sm

    svc._handle_system_response("Deferred", "desktop:other")

    assert model.rowCount() == 0
    sm.get_or_create.assert_called_once_with("desktop:other")
    session.add_message.assert_called_once_with(
        "user",
        "Deferred",
        status="done",
        _source="desktop-system",
        entrance_style="system",
    )


def test_system_response_persist_uses_async_runner_and_skips_sync_save():
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import ChatService

    class _FakeAsyncRunner(AsyncioRunner):
        def __init__(self) -> None:
            super().__init__()
            self.submitted: int = 0

        def submit(self, coro: Coroutine[Any, Any, _T]) -> concurrent.futures.Future[_T]:
            self.submitted += 1
            coro.close()
            fut: concurrent.futures.Future[_T] = concurrent.futures.Future()
            fut.set_result(cast(_T, None))
            return fut

    model = ChatMessageModel()
    runner = _FakeAsyncRunner()
    svc = ChatService(model, runner)
    _LIVE_CHAT_SERVICES.append(svc)

    sm = MagicMock()
    svc._session_manager = sm

    svc._append_transient_system_message("Deferred", session_key="desktop:other", show_in_ui=False)

    assert runner.submitted == 1
    sm.get_or_create.assert_not_called()


def test_transient_greeting_persisted_with_greeting_style() -> None:
    svc, _model = make_service()
    session = MagicMock()
    sm = MagicMock()
    sm.get_or_create.return_value = session
    svc._session_manager = sm

    svc._append_transient_system_message(
        "Hello",
        entrance_style="greeting",
        session_key="desktop:other",
        show_in_ui=False,
    )

    session.add_message.assert_called_once_with(
        "user",
        "Hello",
        status="done",
        _source="desktop-system",
        entrance_style="greeting",
    )


def test_transient_startup_onboarding_persisted_as_assistant() -> None:
    svc, _model = make_service()
    session = MagicMock()
    sm = MagicMock()
    sm.get_or_create.return_value = session
    svc._session_manager = sm

    svc._append_transient_assistant_message(
        "Hello",
        session_key="desktop:other",
        show_in_ui=False,
    )

    session.add_message.assert_called_once_with(
        "assistant",
        "Hello",
        status="done",
        format="markdown",
    )
    sm.update_metadata_only.assert_not_called()


def test_transient_assistant_marks_seen_when_shown_in_active_session() -> None:
    svc, model = make_service()
    session = MagicMock()
    sm = MagicMock()
    sm.get_or_create.return_value = session
    key = "desktop:local::s1"
    svc._session_manager = sm
    svc._session_key = key
    svc._committed_session_key = key

    svc._append_transient_assistant_message("Hello", session_key=key, show_in_ui=True)

    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "assistant"
    sm.update_metadata_only.assert_called_once()


def test_desktop_startup_greeting_queued_until_startup_session_ready() -> None:
    svc, _model = make_service()
    key = "desktop:local::s1"
    svc._session_manager = MagicMock()
    svc._session_key = key
    svc._desired_session_key = key
    svc._committed_session_key = key
    svc._startupMessage.emit(
        DesktopStartupMessage(content="Hello", role="system", entrance_style="greeting")
    )

    assert _model.rowCount() == 0
    assert len(svc._startup_pending) == 1

    svc.notifyStartupSessionReady(key)

    assert _model.rowCount() == 0
    assert len(svc._startup_pending) == 1

    svc._handle_history_result(True, "", (key, 0, (0, ""), []))

    assert _model.rowCount() == 1
    assert _model._messages[0]["role"] == "system"
    assert _model._messages[0]["content"] == "Hello"
    assert _model._messages[0]["entrancestyle"] == "greeting"
    assert not svc._startup_pending


def test_desktop_onboarding_message_queued_until_startup_session_ready() -> None:
    svc, _model = make_service()
    key = "desktop:local::s1"
    svc._session_manager = MagicMock()
    svc._session_key = key
    svc._desired_session_key = key
    svc._committed_session_key = key
    svc._startupMessage.emit(
        DesktopStartupMessage(
            content="Hello",
            role="assistant",
            entrance_style="assistantReceived",
        )
    )

    assert _model.rowCount() == 0
    assert len(svc._startup_pending) == 1

    svc.notifyStartupSessionReady(key)

    assert _model.rowCount() == 0
    assert len(svc._startup_pending) == 1

    svc._handle_history_result(True, "", (key, 0, (0, ""), []))

    assert _model.rowCount() == 1
    assert _model._messages[0]["role"] == "assistant"
    assert _model._messages[0]["content"] == "Hello"
    assert _model._messages[0]["entrancestyle"] == "assistantReceived"
    assert not svc._startup_pending


def test_startup_message_waits_for_history_apply_before_flushing() -> None:
    svc, model = make_service()
    key = "desktop:local::s1"
    svc._session_manager = MagicMock()
    svc._session_key = key
    svc._desired_session_key = key
    svc._committed_session_key = key
    svc.notifyStartupSessionReady(key)

    svc._startupMessage.emit(
        DesktopStartupMessage(content="Hello", role="assistant", entrance_style="assistantReceived")
    )

    assert model.rowCount() == 0
    assert len(svc._startup_pending) == 1

    svc._handle_history_result(True, "", (key, 0, (0, ""), []))

    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "assistant"
    assert model._messages[0]["content"] == "Hello"
    assert not svc._startup_pending


def test_system_response_empty_ignored():
    """Empty system response should be silently ignored."""
    svc, model = make_service()
    svc._handle_system_response("")
    assert model.rowCount() == 0


def test_handle_init_result_sets_gateway_summary_without_chat_message() -> None:
    svc, model = make_service()
    session_manager = MagicMock()
    svc._cron_status = {"jobs": 1}

    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])

    assert svc.state == "running"
    detail = str(svc.property("gatewayDetail"))
    assert detail.startswith("✓ Gateway started")
    assert svc.property("gatewayDetailIsError") is False
    assert "channels: telegram, imessage" in detail
    assert "cron: 1 jobs" in detail
    assert "heartbeat: every 30m" in detail
    assert model.rowCount() == 0


def test_channel_error_updates_gateway_detail_without_chat_message() -> None:
    svc, model = make_service()

    svc._handle_channel_error("start_failed", "telegram", "bad token")

    assert model.rowCount() == 0
    assert svc.lastError == svc._format_channel_error("start_failed", "telegram", "bad token")
    assert svc.property("gatewayDetailIsError") is True
    assert "telegram" in str(svc.property("gatewayDetail"))


def test_init_summary_does_not_override_existing_gateway_error() -> None:
    svc, model = make_service()
    session_manager = MagicMock()
    svc._cron_status = {"jobs": 1}

    svc._handle_channel_error("start_failed", "telegram", "bad token")
    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])

    assert model.rowCount() == 0
    assert svc.lastError == svc._format_channel_error("start_failed", "telegram", "bad token")
    assert svc.property("gatewayDetailIsError") is True
    assert "bad token" in str(svc.property("gatewayDetail"))


def test_start_clears_previous_gateway_detail() -> None:
    svc, _model = make_service()
    svc._set_gateway_detail("boom", error="boom")

    with patch.object(svc, "_init_gateway", return_value=None):
        svc.start()

    assert svc.lastError == ""
    assert svc.property("gatewayDetail") == ""


def test_progress_split_creates_new_bubble_on_next_delta():
    svc, model = make_service()
    row0 = model.append_assistant("", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = False

    svc._handle_progress_update(-1, "first")
    svc._handle_progress_update(-2, "")
    svc._handle_progress_update(-1, "second")

    assert model.rowCount() == 2
    assert model._messages[0]["content"] == "first"
    assert model._messages[0]["status"] == "done"
    assert model._messages[1]["content"] == "second"
    assert model._messages[1]["status"] == "typing"
    assert svc._active_streaming_row == 1


def test_pending_split_without_previous_content_does_not_split_mid_iteration():
    svc, model = make_service()
    row0 = model.append_assistant("", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = False

    svc._handle_progress_update(-2, "")
    svc._handle_progress_update(-1, "a")
    svc._handle_progress_update(-1, "ab")

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "ab"
    assert model._messages[0]["status"] == "typing"
    assert svc._pending_split is False


def test_tool_hint_after_content_creates_dedicated_typing_bubble():
    svc, model = make_service()
    row0 = model.append_assistant("working", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = True

    svc._handle_tool_hint_update("running tool")

    assert model.rowCount() == 2
    assert model._messages[0]["status"] == "done"
    assert model._messages[1]["status"] == "typing"
    assert model._messages[1]["content"] == ""
    assert svc._active_streaming_row == 1
    assert svc._active_has_content is False


def test_tool_hint_without_content_does_not_create_extra_bubble():
    svc, model = make_service()
    row0 = model.append_assistant("", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = False

    svc._handle_tool_hint_update("running tool")

    assert model.rowCount() == 1
    assert svc._active_streaming_row == 0


def test_tool_hint_ignored_when_pending_split():
    svc, model = make_service()
    row0 = model.append_assistant("working", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = True
    svc._pending_split = True

    svc._handle_tool_hint_update("running tool")

    assert model.rowCount() == 1
    assert model._messages[0]["status"] == "typing"
    assert svc._active_streaming_row == 0


def test_send_result_pending_split_with_final_content_creates_new_final_bubble():
    svc, model = make_service()
    row0 = model.append_assistant("first", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = True
    svc._pending_split = True

    svc._handle_send_result(row0, True, "final")

    assert model.rowCount() == 2
    assert model._messages[0]["content"] == "first"
    assert model._messages[0]["status"] == "done"
    assert model._messages[1]["content"] == "final"
    assert model._messages[1]["status"] == "done"


def test_send_result_pending_split_without_final_content_no_empty_done_bubble():
    svc, model = make_service()
    row0 = model.append_assistant("first", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = True
    svc._pending_split = True

    svc._handle_send_result(row0, True, "")

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "first"
    assert model._messages[0]["status"] == "done"


def test_send_result_provider_error_switches_active_bubble_to_plain_text():
    svc, model = make_service()
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row

    svc._handle_send_result(row, True, "Error calling LLM: <b>forbidden</b>")

    assert model._messages[0]["format"] == "plain"
    assert model._messages[0]["status"] == "error"
    assert model._messages[0]["content"] == "Error calling LLM: <b>forbidden</b>"


def test_send_result_transport_error_switches_active_bubble_to_plain_text():
    svc, model = make_service()
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row

    svc._handle_send_result(row, False, "Error: network down")

    assert model._messages[0]["format"] == "plain"
    assert model._messages[0]["status"] == "error"
    assert model._messages[0]["content"] == "Error: network down"


def test_send_result_does_not_mark_seen_for_background_session():
    svc, model = make_service()
    svc._session_manager = object()
    svc._committed_session_key = "desktop:new"
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "desktop:old"

    svc._handle_send_result(row, True, "ok")

    cast(MagicMock, svc._runner.submit).assert_not_called()


def test_send_result_marks_seen_for_active_session():
    svc, model = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._committed_session_key = "desktop:active"
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "desktop:active"

    svc._handle_send_result(row, True, "ok")

    sm.update_metadata_only.assert_called_once()
    assert sm.update_metadata_only.call_args.kwargs == {"emit_change": False}


def test_set_session_manager_registers_change_listener():
    svc, _model = make_service()
    sm = _SessionManagerWithListeners()

    svc.setSessionManager(sm)

    assert svc._on_session_change in sm.listeners


def test_set_session_manager_replaces_previous_change_listener():
    svc, _model = make_service()
    old_sm = _SessionManagerWithListeners()
    new_sm = _SessionManagerWithListeners()

    svc.setSessionManager(old_sm)
    svc.setSessionManager(new_sm)

    assert svc._on_session_change not in old_sm.listeners
    assert svc._on_session_change in new_sm.listeners


def test_session_change_reloads_active_history_for_message_commit():
    svc, _model = make_service()
    sm = _SessionManagerWithListeners()
    svc.setSessionManager(sm)
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._current_nav_id = 7

    called = []
    svc._cancel_history_future = lambda: called.append(("cancel",))
    svc._request_history_load = lambda key, nav_id, show_loading=None: called.append(
        (key, nav_id, show_loading)
    )

    sm.emit("desktop:local", "messages")

    assert called == [("cancel",), ("desktop:local", 7, False)]


def test_session_change_ignores_metadata_commit_for_active_history():
    svc, _model = make_service()
    sm = _SessionManagerWithListeners()
    svc.setSessionManager(sm)
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"

    called = []
    svc._request_history_load = lambda *args, **kwargs: called.append((args, kwargs))

    sm.emit("desktop:local", "metadata")

    assert called == []


def test_handle_init_result_registers_actual_session_manager_listener():
    svc, _model = make_service()
    early_sm = _SessionManagerWithListeners()
    actual_sm = _SessionManagerWithListeners()
    svc.setSessionManager(early_sm)

    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", actual_sm, [])

    assert svc._on_session_change not in early_sm.listeners
    assert svc._on_session_change in actual_sm.listeners


def test_handle_history_result_ignores_stale_session_payload():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    svc._desired_session_key = "imessage:active"

    svc._handle_history_result(
        True,
        "",
        ("imessage:other", [{"role": "user", "content": "hello", "timestamp": "t"}]),
    )

    assert model.rowCount() == 0


def test_handle_history_result_skips_reload_when_signature_unchanged():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    svc._desired_session_key = "imessage:active"
    payload = ("imessage:active", [{"role": "user", "content": "hello", "timestamp": "t"}])

    with patch.object(model, "load_history", wraps=model.load_history) as mocked:
        svc._handle_history_result(True, "", payload)
        svc._handle_history_result(True, "", payload)

    assert mocked.call_count == 1


def test_set_session_key_switches_immediately_while_processing():
    svc, model = make_service()
    svc._session_manager = object()
    svc._processing = True
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "imessage:active"
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("imessage:new")

    assert svc._desired_session_key == "imessage:new"
    assert svc._committed_session_key == "imessage:new"
    assert svc._current_nav_id == 1
    assert svc._active_streaming_row == -1
    assert model.rowCount() == 0
    assert called == ["imessage:new"]


def test_handle_history_result_applies_while_streaming_when_generation_matches():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    svc._desired_session_key = "imessage:active"
    svc._processing = True
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "imessage:active"
    svc._current_nav_id = 1

    svc._handle_history_result(
        True,
        "",
        ("imessage:active", 1, [{"role": "user", "content": "hello", "timestamp": "t"}]),
    )

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "hello"


def test_handle_history_result_rejects_stale_nav_payload():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    svc._desired_session_key = "imessage:active"
    svc._current_nav_id = 2
    prepared = [
        {
            "id": 1,
            "createdat": 0,
            "role": "assistant",
            "content": "hello",
            "format": "plain",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
        }
    ]
    sig = svc._history_signature(prepared)

    svc._handle_history_result(True, "", ("imessage:active", 1, sig, prepared))

    assert model.rowCount() == 0


def test_switch_while_streaming_does_not_show_old_session_content():
    svc, model = make_service()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "desktop:old"
    svc._processing = True

    svc.setSessionKey("desktop:new")
    assert model.rowCount() == 0

    svc._handle_progress_update(-1, "old-stream")
    svc._handle_send_result(row, True, "old-final")

    assert model.rowCount() == 0
    assert svc._committed_session_key == "desktop:new"


def test_set_session_key_same_key_still_loads_when_history_not_initialized():
    svc, _ = make_service()
    sm = MagicMock()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._history_initialized = False
    svc._processing = True
    svc._session_manager = sm
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("desktop:local")

    assert called == ["desktop:local"]
    assert svc._current_nav_id == 1
    sm.update_metadata_only.assert_called_once()
    assert sm.update_metadata_only.call_args.kwargs == {"emit_change": False}


def test_set_session_key_same_key_ignored_when_history_inflight():
    svc, _ = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._history_initialized = False
    svc._history_future = object()
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("desktop:local")

    assert called == []
    assert svc._current_nav_id == 0
    sm.update_metadata_only.assert_not_called()


def test_set_session_key_marks_seen_before_history_reload_for_new_session():
    svc, _ = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._history_initialized = True
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("desktop:new")

    assert called == ["desktop:new"]
    sm.update_metadata_only.assert_called_once()
    assert sm.update_metadata_only.call_args.kwargs == {"emit_change": False}


def test_set_session_key_empty_clears_visible_history_without_reloading():
    svc, model = make_service()
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._history_initialized = True
    model.append_assistant("existing", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("")

    assert svc._session_key == ""
    assert svc._desired_session_key == ""
    assert svc._committed_session_key == ""
    assert svc.historyLoading is False
    assert model.rowCount() == 0
    assert called == []


def test_set_session_key_uses_cached_snapshot_for_instant_render():
    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import _HistorySnapshot

    svc, model = make_service()
    cached_key = "desktop:new"
    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "cached", "timestamp": "t"}]
    )
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._history_cache[cached_key] = _HistorySnapshot((len(prepared), "cached"), prepared, True)
    model.append_assistant("old", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey(cached_key)

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "cached"
    assert svc.activeSessionReady is True
    assert svc.activeSessionHasMessages is True
    assert svc.historyLoading is False
    assert called == [(cached_key, False)]


def test_set_session_key_emits_session_view_applied_for_switched_cached_session():
    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import _HistorySnapshot

    svc, _model = make_service()
    cached_key = "desktop:new"
    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "cached", "timestamp": "t"}]
    )
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._history_cache[cached_key] = _HistorySnapshot((len(prepared), "cached"), prepared, True)
    svc._request_history_load = lambda *_args, **_kwargs: None

    applied: list[str] = []
    svc.sessionViewApplied.connect(applied.append)

    svc.setSessionKey(cached_key)

    assert applied == [cached_key]


def test_set_session_key_same_session_does_not_emit_session_view_applied():
    svc, _model = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._history_initialized = False
    svc._request_history_load = lambda *_args, **_kwargs: None

    applied: list[str] = []
    svc.sessionViewApplied.connect(applied.append)

    svc.setSessionKey("desktop:local")

    assert applied == []


def test_set_session_key_uses_manager_tail_snapshot_before_async_reload():
    svc, model = make_service()
    raw_tail = [{"role": "assistant", "content": "from-manager", "timestamp": "t"}]
    sm = MagicMock()
    sm.peek_tail_messages.return_value = raw_tail
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    model.append_assistant("old", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey("desktop:new")

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "from-manager"
    assert svc.activeSessionReady is True
    assert svc.activeSessionHasMessages is True
    assert svc.historyLoading is False
    assert called == [("desktop:new", False)]


def test_set_session_key_without_memory_snapshot_uses_async_load_path():
    svc, model = make_service()
    sm = MagicMock()
    sm.peek_tail_messages.return_value = None
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    model.append_assistant("old", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey("desktop:new")

    assert model.rowCount() == 0
    assert svc.activeSessionReady is False
    assert svc.activeSessionHasMessages is False
    assert called == [("desktop:new", True)]


def test_set_session_key_uses_empty_manager_tail_snapshot_without_loading():
    svc, model = make_service()
    sm = MagicMock()
    sm.peek_tail_messages.return_value = []
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    model.append_assistant("old", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey("desktop:empty")

    assert model.rowCount() == 0
    assert svc.activeSessionReady is True
    assert svc.activeSessionHasMessages is False
    assert svc.historyLoading is False
    assert called == [("desktop:empty", False)]


def test_set_session_key_uses_empty_session_summary_without_tail_read():
    svc, model = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc.setSessionSummary("desktop:empty", 0, False)
    model.append_assistant("old", status="done")
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey("desktop:empty")

    sm.peek_tail_messages.assert_not_called()
    assert model.rowCount() == 0
    assert svc.activeSessionReady is True
    assert svc.activeSessionHasMessages is False
    assert svc.historyLoading is False
    assert called == [("desktop:empty", False)]


def test_empty_session_summary_still_allows_silent_history_correction():
    from app.backend.chat import ChatMessageModel

    svc, model = make_service()
    sm = MagicMock()
    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._current_nav_id = 1
    svc.setSessionSummary("desktop:empty", 0, False)
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey("desktop:empty")
    assert called == [("desktop:empty", False)]

    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "arrived", "timestamp": "t"}]
    )
    svc._handle_history_result(
        True,
        "",
        ("desktop:empty", svc._current_nav_id, (1, "arrived"), prepared, True),
    )

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "arrived"
    assert svc.activeSessionHasMessages is True


def test_set_session_key_does_not_render_uncommitted_tail_after_failed_save(tmp_path):
    from app.backend.chat import ChatMessageModel
    from bao.session.manager import SessionManager

    svc, model = make_service()
    sm = SessionManager(tmp_path)
    key = "desktop:local::rollback-tail"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)
    session.add_message("assistant", "new")

    with patch.object(sm._msg_table(), "add", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            sm.save(session)

    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey(key)

    assert model.rowCount() == 0
    assert called == [(key, True)]

    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "old", "timestamp": "t"}]
    )
    svc._handle_history_result(True, "", (key, svc._current_nav_id, (1, "old"), prepared, True))

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "old"


def test_set_session_key_after_failed_clear_save_keeps_previous_tail(tmp_path):
    from app.backend.chat import ChatMessageModel
    from bao.session.manager import SessionManager

    svc, model = make_service()
    sm = SessionManager(tmp_path)
    key = "desktop:local::rollback-clear"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)
    session.clear()

    with patch.object(sm, "_write_display_tail_row", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            sm.save(session)

    svc._session_manager = sm
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(
        (key, kwargs.get("show_loading"))
    )

    svc.setSessionKey(key)

    assert model.rowCount() == 0
    assert called == [(key, True)]

    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "old", "timestamp": "t"}]
    )
    svc._handle_history_result(True, "", (key, svc._current_nav_id, (1, "old"), prepared, True))

    assert model.rowCount() == 1
    assert model._messages[0]["content"] == "old"


def test_handle_history_result_marks_empty_session_ready_without_messages():
    svc, _model = make_service()
    key = "desktop:local"
    svc._session_key = key
    svc._desired_session_key = key
    svc._current_nav_id = 1

    svc._handle_history_result(True, "", (key, 1, (0, ""), [], False))

    assert svc.activeSessionReady is True
    assert svc.activeSessionHasMessages is False


def test_non_active_session_message_invalidates_cached_snapshot():
    from app.backend.gateway import _HistorySnapshot

    svc, _model = make_service()
    stale_key = "desktop:stale"
    active_key = "desktop:active"
    svc._desired_session_key = active_key
    svc._committed_session_key = active_key
    svc._history_cache[stale_key] = _HistorySnapshot((1, "stale"), [], False)

    svc._handle_session_change(SessionChangeEvent(session_key=stale_key, kind="messages"))

    assert stale_key not in svc._history_cache


def test_load_history_uses_display_history_for_ui_model():
    svc, _ = make_service()
    session = MagicMock()
    session.get_display_history.return_value = [
        {"role": "assistant", "content": "a1", "format": "markdown"}
    ]
    svc._session_manager = MagicMock()
    svc._session_manager.get_or_create.return_value = session

    payload = asyncio.run(svc._load_history("desktop:local", 3, 200))

    assert payload[0] == "desktop:local"
    assert payload[1] == 3
    assert payload[3] == [
        {
            "id": 1,
            "createdat": 0,
            "role": "assistant",
            "content": "a1",
            "format": "markdown",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
            "dividertext": "",
        }
    ]
    assert payload[4] is True
    session.get_display_history.assert_called_once()


def test_handle_history_result_does_not_reset_when_only_entrance_differs():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    _ = model.append_assistant("hello", status="done", entrance_pending=True)
    prepared = [
        {
            "id": 1,
            "createdat": 0,
            "role": "assistant",
            "content": "hello",
            "format": "markdown",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
        }
    ]
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    svc._history_initialized = True
    svc._history_fingerprint = (1, "stale")
    svc._current_nav_id = 1

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []


def test_handle_history_result_does_not_reset_when_only_system_entrance_differs():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    _ = model.append_system("gateway started", entrance_style="system", entrance_pending=True)
    prepared = [
        {
            "id": 1,
            "createdat": 0,
            "role": "system",
            "content": "gateway started",
            "format": "plain",
            "status": "done",
            "entrancestyle": "greeting",
            "entrancepending": False,
        }
    ]
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    svc._history_initialized = True
    svc._history_fingerprint = (1, "stale")
    svc._current_nav_id = 1

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model._messages[0]["entrancestyle"] == "greeting"


def test_handle_history_result_preserves_transient_typing_tail_without_reset():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (1, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row

    prepared = [
        {
            "id": 1,
            "createdat": 0,
            "role": "user",
            "content": "hello",
            "format": "plain",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
        }
    ]
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model.rowCount() == 2
    assert model._messages[0]["content"] == "hello"
    assert model._messages[1]["role"] == "assistant"
    assert model._messages[1]["status"] == "typing"


def test_handle_history_result_updates_active_assistant_without_reset_on_finalize_race():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (2, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row

    prepared = [
        {
            "id": 1,
            "createdat": 0,
            "role": "user",
            "content": "hello",
            "format": "plain",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
        },
        {
            "id": 2,
            "createdat": 0,
            "role": "assistant",
            "content": "world",
            "format": "markdown",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
        },
    ]
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model.rowCount() == 2
    assert model._messages[1]["content"] == "world"
    assert model._messages[1]["status"] == "done"


def test_handle_history_result_preserves_transient_tail_after_tool_row_without_reset():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (2, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    _ = model.append_assistant("working", status="done")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [{"role": "user", "content": "hello"}, {"role": "tool", "content": "running tool"}]
    )
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model.rowCount() == 4
    assert model._messages[1]["role"] == "system"
    assert model._messages[2]["content"] == "working"
    assert model._messages[3]["status"] == "typing"
    assert svc._active_streaming_row == 3


def test_handle_history_result_reconciles_tool_row_and_final_assistant_without_reset():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (3, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    _ = model.append_assistant("working", status="done")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "running tool"},
            {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model.rowCount() == 3
    assert model._messages[1]["role"] == "system"
    assert model._messages[2]["content"] == "final"
    assert model._messages[2]["status"] == "done"
    assert svc._active_streaming_row == 2


def test_handle_history_result_reconciles_after_send_result_wins_race():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (3, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    _ = model.append_assistant("working", status="done")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row
    svc._handle_send_result(typing_row, True, "final")

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "running tool"},
            {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))

    assert resets == []
    assert model.rowCount() == 3
    assert model._messages[1]["role"] == "system"
    assert model._messages[2]["content"] == "final"
    assert model._messages[2]["status"] == "done"


def test_send_result_after_history_reconcile_uses_shifted_active_row():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (3, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    _ = model.append_assistant("working", status="done")
    typing_row = model.append_assistant("", status="typing")
    svc._active_streaming_row = typing_row

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "running tool"},
            {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    statuses = []
    svc.statusUpdated.connect(lambda row, status: statuses.append((row, status)))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))
    svc._handle_send_result(typing_row, True, "final")

    assert statuses[-1] == (2, "done")


def test_send_result_after_assistant_only_history_split_uses_last_row():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (3, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    typing_row = model.append_assistant("first", status="typing")
    svc._active_streaming_row = typing_row

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "first", "status": "done", "format": "markdown"},
            {"role": "assistant", "content": "second", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    statuses = []
    svc.statusUpdated.connect(lambda row, status: statuses.append((row, status)))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))
    svc._handle_send_result(typing_row, True, "second")

    assert svc._active_streaming_row == -1
    assert statuses[-1] == (2, "done")


def test_history_materialized_split_clears_pending_split_before_send_result():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._active_streaming_session_key = "desktop:local"
    svc._processing = True
    svc._history_initialized = True
    svc._history_fingerprint = (3, "stale")
    svc._current_nav_id = 1

    _ = model.append_user("hello")
    typing_row = model.append_assistant("first", status="typing")
    svc._active_streaming_row = typing_row
    svc._active_has_content = True
    svc._pending_split = True

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "first", "status": "done", "format": "markdown"},
            {"role": "assistant", "content": "second", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    statuses = []
    svc.statusUpdated.connect(lambda row, status: statuses.append((row, status)))

    svc._handle_history_result(True, "", ("desktop:local", 1, sig, prepared))
    svc._handle_send_result(typing_row, True, "second")

    assert model.rowCount() == 3
    assert svc._active_streaming_row == -1
    assert svc._pending_split is False
    assert statuses[-1] == (2, "done")


def test_switch_back_to_streaming_session_rebinds_active_row_to_last_assistant():
    svc, model = make_service()
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._active_streaming_session_key = "desktop:old"
    svc._processing = True
    row = model.append_assistant("first", status="typing")
    svc._active_streaming_row = row

    svc.setSessionKey("desktop:new")
    svc.setSessionKey("desktop:old")

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "assistant", "content": "first", "status": "done", "format": "markdown"},
            {"role": "assistant", "content": "second", "status": "done", "format": "markdown"},
        ]
    )
    sig = svc._history_signature(prepared)
    statuses = []
    svc.statusUpdated.connect(lambda active_row, status: statuses.append((active_row, status)))

    svc._handle_history_result(True, "", ("desktop:old", svc._current_nav_id, sig, prepared))
    svc._handle_send_result(row, True, "second")

    assert statuses[-1] == (1, "done")


def test_switch_back_to_streaming_session_restores_typing_placeholder_after_latest_user():
    svc, model = make_service()
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._active_streaming_session_key = "desktop:old"
    svc._processing = True
    row = model.append_assistant("first", status="typing")
    svc._active_streaming_row = row

    svc.setSessionKey("desktop:new")
    svc.setSessionKey("desktop:old")

    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "assistant", "content": "older", "status": "done", "format": "markdown"},
            {"role": "user", "content": "hello"},
        ]
    )
    sig = svc._history_signature(prepared)
    statuses = []
    svc.statusUpdated.connect(lambda active_row, status: statuses.append((active_row, status)))

    svc._handle_history_result(True, "", ("desktop:old", svc._current_nav_id, sig, prepared))
    svc._handle_send_result(row, True, "final")

    assert model.rowCount() == 3
    assert model._messages[0]["content"] == "older"
    assert model._messages[1]["role"] == "user"
    assert model._messages[2]["role"] == "assistant"
    assert model._messages[2]["content"] == "final"
    assert statuses[-1] == (2, "done")


def test_send_result_before_switch_back_history_rebind_restores_placeholder():
    svc, model = make_service()
    svc._session_manager = object()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    svc._active_streaming_session_key = "desktop:old"
    svc._processing = True
    row = model.append_assistant("first", status="typing")
    svc._active_streaming_row = row

    svc.setSessionKey("desktop:new")
    svc.setSessionKey("desktop:old")

    statuses = []
    svc.statusUpdated.connect(lambda active_row, status: statuses.append((active_row, status)))

    svc._handle_send_result(row, True, "final")

    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "assistant"
    assert model._messages[0]["content"] == "final"
    assert statuses[-1] == (0, "done")


def test_history_signature_changes_when_earlier_prepared_message_changes():
    svc, _ = make_service()

    old_prepared = [
        {
            "role": "system",
            "content": "welcome",
            "format": "plain",
            "status": "done",
            "entrancestyle": "system",
        },
        {
            "role": "assistant",
            "content": "hello",
            "format": "markdown",
            "status": "done",
            "entrancestyle": "none",
        },
    ]
    new_prepared = [
        {
            "role": "system",
            "content": "welcome",
            "format": "plain",
            "status": "done",
            "entrancestyle": "greeting",
        },
        {
            "role": "assistant",
            "content": "hello",
            "format": "markdown",
            "status": "done",
            "entrancestyle": "none",
        },
    ]

    assert svc._history_signature(old_prepared) != svc._history_signature(new_prepared)


def test_progress_update_does_not_mutate_model_when_session_mismatch():
    svc, model = make_service()
    svc._session_key = "desktop:old"
    svc._desired_session_key = "desktop:old"
    svc._committed_session_key = "desktop:old"
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._active_streaming_session_key = "desktop:old"
    svc._processing = True

    svc.setSessionKey("desktop:new")
    assert model.rowCount() == 0

    svc._handle_progress_update(-1, "streaming content")

    assert model.rowCount() == 0
    assert svc._active_has_content is True
    assert svc._committed_session_key == "desktop:new"
