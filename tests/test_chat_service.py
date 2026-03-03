"""Tests for ChatService state machine and message queue."""

from __future__ import annotations

import asyncio
import importlib
import sys
from unittest.mock import MagicMock, patch

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication


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
    runner = MagicMock()
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

    # Patch _init_gateway to avoid real Bao init
    async def fake_init():
        pass

    with patch.object(svc, "_init_gateway", return_value=fake_init()):
        svc.start()

    assert "starting" in states


def test_double_start_is_noop():
    svc, _ = make_service()
    states = []
    svc.stateChanged.connect(states.append)

    async def fake_init():
        pass

    with patch.object(svc, "_init_gateway", return_value=fake_init()):
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
    assert model._messages[0]["role"] == "assistant"
    assert model._messages[0]["content"] == "Task done"
    assert model._messages[0]["status"] == "done"


def test_system_response_queued_while_processing():
    """System response should be queued when main streaming is active."""
    svc, model = make_service()
    svc._processing = True
    svc._handle_system_response("Queued msg")
    assert model.rowCount() == 0  # not displayed yet
    assert len(svc._pending_system) == 1


def test_system_response_drained_after_send():
    """Pending system responses should drain after send completes."""
    svc, model = make_service()
    svc._processing = True
    svc._pending_system.append("Deferred")
    row = model.append_assistant("reply", status="typing")
    svc._handle_send_result(row, True, "reply")
    assert model._messages[0]["status"] == "done"
    # Deferred system response should now be displayed
    assert model.rowCount() == 2
    assert model._messages[1]["content"] == "Deferred"


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


def test_sync_active_history_requests_reload_when_idle():
    svc, _ = make_service()
    svc._session_manager = object()
    svc._history_initialized = True
    called = []
    svc._request_history_load = lambda key: called.append(key)

    svc._sync_active_history()

    assert called == [svc._session_key]


def test_sync_active_history_skips_while_processing():
    svc, _ = make_service()
    svc._session_manager = object()
    svc._history_initialized = True
    svc._processing = True
    called = []
    svc._request_history_load = lambda key: called.append(key)

    svc._sync_active_history()

    assert called == []


def test_handle_history_result_ignores_stale_session_payload():
    svc, model = make_service()
    svc._session_key = "imessage:active"

    svc._handle_history_result(
        True,
        "",
        ("imessage:other", [{"role": "user", "content": "hello", "timestamp": "t"}]),
    )

    assert model.rowCount() == 0


def test_handle_history_result_skips_reload_when_signature_unchanged():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    payload = ("imessage:active", [{"role": "user", "content": "hello", "timestamp": "t"}])

    with patch.object(model, "load_history", wraps=model.load_history) as mocked:
        svc._handle_history_result(True, "", payload)
        svc._handle_history_result(True, "", payload)

    assert mocked.call_count == 1


def test_set_session_key_deferred_while_processing():
    svc, model = make_service()
    svc._processing = True
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row

    with patch.object(svc, "_apply_session_key") as mocked_apply:
        svc.setSessionKey("imessage:new")
        assert svc._pending_session_key == "imessage:new"
        svc._handle_send_result(row, True, "done")

    mocked_apply.assert_called_once_with("imessage:new")


def test_handle_history_result_defers_when_streaming():
    svc, model = make_service()
    svc._session_key = "imessage:active"
    svc._processing = True
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row
    svc._history_latest_seq = 1
    called = []
    svc._request_history_load = lambda key: called.append(key)

    svc._handle_history_result(
        True,
        "",
        ("imessage:active", 1, [{"role": "user", "content": "hello", "timestamp": "t"}]),
    )
    assert svc._pending_history_refresh is True

    svc._handle_send_result(row, True, "done")

    assert called == ["imessage:active"]


def test_set_session_key_same_key_still_loads_when_history_not_initialized():
    svc, model = make_service()
    svc._session_key = "desktop:local"
    svc._history_initialized = False
    svc._processing = True
    row = model.append_assistant("", status="typing")
    svc._active_streaming_row = row

    with patch.object(svc, "_apply_session_key") as mocked_apply:
        svc.setSessionKey("desktop:local")
        assert svc._pending_session_key == "desktop:local"
        svc._handle_send_result(row, True, "done")

    mocked_apply.assert_called_once_with("desktop:local")


def test_load_history_uses_display_history_for_ui_model():
    svc, _ = make_service()
    session = MagicMock()
    session.get_display_history.return_value = [{"role": "assistant", "content": "a1"}]
    svc._session_manager = MagicMock()
    svc._session_manager.get_or_create.return_value = session

    payload = asyncio.run(svc._load_history("desktop:local", 3))

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
        }
    ]
    session.get_display_history.assert_called_once()
