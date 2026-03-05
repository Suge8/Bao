"""Tests for ChatService state machine and message queue."""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar, cast
from unittest.mock import MagicMock, patch

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication
_T = TypeVar("_T")


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
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
    assert "boom" in errors
    assert "error" in states


def test_show_system_response_immediate():
    """System response should appear immediately when not processing."""
    svc, model = make_service()
    svc._show_system_response("Task done")
    assert model.rowCount() == 1
    assert model._messages[0]["role"] == "system"
    assert model._messages[0]["content"] == "Task done"
    assert model._messages[0]["status"] == "done"


def test_system_response_queued_while_processing():
    """System response should be queued when main streaming is active."""
    svc, model = make_service()
    svc._processing = True
    svc._handle_system_response("Queued msg")
    assert model.rowCount() == 0  # not displayed yet
    assert len(svc._pending_system) == 1
    assert svc._pending_system[0] == ("Queued msg", "assistantReceived", "desktop:local")


def test_system_response_drained_after_send():
    """Pending system responses should drain after send completes."""
    svc, model = make_service()
    svc._processing = True
    svc._pending_system.append(("Deferred", "assistantReceived", svc._session_key))
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


def test_desktop_startup_greeting_queued_until_startup_session_ready() -> None:
    svc, _model = make_service()
    captured: list[tuple[str, str]] = []
    svc._systemResponse.connect(lambda content, key: captured.append((content, key)))

    svc._startupGreeting.emit("Hello")
    assert captured == []

    svc.notifyStartupSessionReady("desktop:local::s1")
    assert captured == [("Hello", "desktop:local::s1")]


def test_system_response_empty_ignored():
    """Empty system response should be silently ignored."""
    svc, model = make_service()
    svc._handle_system_response("")
    assert model.rowCount() == 0


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
            "entranceconsumed": True,
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
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    svc._committed_session_key = "desktop:local"
    svc._history_initialized = False
    svc._processing = True
    svc._session_manager = object()
    called = []
    svc._request_history_load = lambda key, *_args, **kwargs: called.append(key)

    svc.setSessionKey("desktop:local")

    assert called == ["desktop:local"]
    assert svc._current_nav_id == 1


def test_set_session_key_same_key_ignored_when_history_inflight():
    svc, _ = make_service()
    svc._session_manager = object()
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


def test_load_history_uses_display_history_for_ui_model():
    svc, _ = make_service()
    session = MagicMock()
    session.get_display_history.return_value = [{"role": "assistant", "content": "a1"}]
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
            "format": "plain",
            "status": "done",
            "entrancestyle": "none",
            "entrancepending": False,
            "entranceconsumed": True,
        }
    ]
    session.get_display_history.assert_called_once()


def test_handle_history_result_does_not_reset_when_only_entrance_differs():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._desired_session_key = "desktop:local"
    row = model.append_assistant("hello", status="done", entrance_pending=True)
    model.mark_entrance_pending(row)
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
            "entranceconsumed": True,
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
