"""Tests for ChatService state machine and message queue."""

from __future__ import annotations

import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


from app.backend.chat import ChatMessageModel
from app.backend.gateway import ChatService


def make_service():
    model = ChatMessageModel()
    runner = MagicMock()
    svc = ChatService(model, runner)
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

    # Patch _init_gateway to avoid real bao init
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
