# ruff: noqa: F401,F403,F405,I001
from __future__ import annotations

from tests._chat_service_testkit import *

def test_set_error_changes_state():
    svc, _ = make_service()
    errors = []
    states = []
    svc.errorChanged.connect(errors.append)
    svc.stateChanged.connect(states.append)
    svc._set_error("boom")
    assert svc.state == "error"
    assert svc.lastError == "boom"
    assert svc.property("hubDetail") == "boom"
    assert svc.property("hubDetailIsError") is True
    assert "boom" in errors
    assert "error" in states


def test_set_error_does_not_append_chat_message():
    svc, model = make_service()

    svc._set_error("boom")

    assert model.rowCount() == 0


def test_configured_hub_channels_project_idle_channels() -> None:
    svc, _model = make_service()

    svc.setConfiguredHubChannels(["imessage", "telegram", "imessage"])

    channels = svc.property("hubChannels")
    assert [item["channel"] for item in channels] == ["telegram", "imessage"]
    assert all(item["state"] == "idle" for item in channels)


def test_hub_channels_mark_only_failed_channel_as_error() -> None:
    svc, _model = make_service()
    session_manager = MagicMock()
    svc.setConfiguredHubChannels(["telegram", "imessage"])
    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])
    svc._handle_channel_error("start_failed", "telegram", "bad token")

    channels = {item["channel"]: item for item in svc.property("hubChannels")}
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
    from app.backend.hub import ChatService

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

    svc._append_transient_assistant_message(
        "Hello",
        status="done",
        entrance_style="greeting",
        session_key="desktop:other",
        show_in_ui=False,
    )

    session.add_message.assert_called_once_with(
        "assistant",
        "Hello",
        status="done",
        format="markdown",
        entrance_style="greeting",
    )
    sm.save.assert_called_once_with(session, emit_change=True)
    sm.update_metadata_only.assert_not_called()


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
        entrance_style="assistantReceived",
    )
    sm.save.assert_called_once_with(session, emit_change=True)
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
    sm.mark_desktop_seen_ai.assert_called_once_with(
        key,
        emit_change=False,
        metadata_updates=None,
        clear_running=False,
    )
    sm.set_session_running.assert_not_called()
    sm.update_metadata_only.assert_not_called()


def test_desktop_startup_greeting_queued_until_startup_session_ready() -> None:
    svc, _model = make_service()
    key = "desktop:local::s1"
    svc._session_manager = MagicMock()
    svc._session_key = key
    svc._desired_session_key = key
    svc._committed_session_key = key
    svc._startupMessage.emit(
        DesktopStartupMessage(content="Hello", role="assistant", entrance_style="greeting")
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
    assert _model._messages[0]["entrancestyle"] == "greeting"
    assert not svc._startup_pending
