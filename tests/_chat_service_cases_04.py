# ruff: noqa: F401,F403,F405,I001
from __future__ import annotations

from tests._chat_service_testkit import *

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


def test_default_startup_session_key_prefers_desktop_target_over_current_external_session() -> None:
    svc, _model = make_service()
    svc._session_key = "imessage:13800138000"
    svc._startup_target_key = "desktop:local::s1"

    assert svc._default_startup_session_key() == "desktop:local::s1"


def test_default_startup_session_key_ignores_current_external_session_without_desktop_target() -> (
    None
):
    svc, _model = make_service()
    svc._session_key = "imessage:13800138000"
    svc._startup_target_key = ""

    assert svc._default_startup_session_key() == ""


def test_desktop_startup_message_persists_to_desktop_target_when_current_view_is_external() -> None:
    svc, model = make_service()
    svc._session_manager = MagicMock()
    svc._session_key = "imessage:13800138000"
    svc._desired_session_key = "imessage:13800138000"
    svc._committed_session_key = "imessage:13800138000"
    svc._history_initialized = True
    svc.notifyStartupSessionReady("desktop:local::s1")

    scheduled: list[tuple[str, str, str, str, bool, bool]] = []

    def _schedule(*args, **kwargs) -> None:
        scheduled.append(
            (
                args[0],
                args[1],
                args[2],
                kwargs.get("entrance_style", "assistantReceived"),
                kwargs.get("emit_change", False),
                kwargs.get("mark_seen", False),
            )
        )

    svc._schedule_assistant_message_persist = _schedule
    svc._startupMessage.emit(
        DesktopStartupMessage(content="Hello", role="assistant", entrance_style="greeting")
    )

    assert model.rowCount() == 0
    assert scheduled == [("desktop:local::s1", "Hello", "done", "greeting", True, False)]


def test_system_response_empty_ignored():
    """Empty system response should be silently ignored."""
    svc, model = make_service()
    svc._handle_system_response("")
    assert model.rowCount() == 0


def test_handle_init_result_sets_hub_summary_without_chat_message() -> None:
    svc, model = make_service()
    session_manager = MagicMock()
    svc._cron_status = {"jobs": 1}

    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])

    assert svc.state == "running"
    detail = str(svc.property("hubDetail"))
    assert detail.startswith("✓ Hub started")
    assert svc.property("hubDetailIsError") is False
    assert "channels: telegram, imessage" in detail
    assert "cron: 1 jobs" in detail
    assert "heartbeat: every 30m" in detail
    assert model.rowCount() == 0


def test_channel_error_updates_hub_detail_without_chat_message() -> None:
    svc, model = make_service()

    svc._handle_channel_error("start_failed", "telegram", "bad token")

    assert model.rowCount() == 0
    assert svc.lastError == svc._format_channel_error("start_failed", "telegram", "bad token")
    assert svc.property("hubDetailIsError") is True
    assert "telegram" in str(svc.property("hubDetail"))


def test_init_summary_does_not_override_existing_hub_error() -> None:
    svc, model = make_service()
    session_manager = MagicMock()
    svc._cron_status = {"jobs": 1}

    svc._handle_channel_error("start_failed", "telegram", "bad token")
    svc._lifecycle_request_id = 1
    svc._handle_init_result(1, True, "", session_manager, ["telegram", "imessage"])

    assert model.rowCount() == 0
    assert svc.lastError == svc._format_channel_error("start_failed", "telegram", "bad token")
    assert svc.property("hubDetailIsError") is True
    assert "bad token" in str(svc.property("hubDetail"))


def test_start_clears_previous_hub_detail() -> None:
    svc, _model = make_service()
    svc._set_hub_detail("boom", error="boom")
    pending_init: concurrent.futures.Future[object] = concurrent.futures.Future()

    def _submit(coro: Coroutine[Any, Any, object]) -> concurrent.futures.Future[object]:
        coro.close()
        return pending_init

    svc._runner.submit = MagicMock(side_effect=_submit)
    svc.start()

    assert svc.lastError == ""
    assert svc.property("hubDetail") == ""


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

    svc._handle_tool_hint_update("🔎 Search Web: latest ai news")

    assert model.rowCount() == 3
    assert model._messages[0]["status"] == "done"
    assert model._messages[1]["status"] == "done"
    assert model._messages[1]["content"] == "🔎 Search Web: latest ai news"
    assert model._messages[2]["status"] == "typing"
    assert model._messages[2]["content"] == ""
    assert svc._active_streaming_row == 2
    assert svc._active_has_content is False


def test_tool_hint_without_content_does_not_create_extra_bubble():
    svc, model = make_service()
    row0 = model.append_assistant("", status="typing")
    svc._active_streaming_row = row0
    svc._active_has_content = False

    svc._handle_tool_hint_update("🌐 Fetch Web Page: example.com/news")

    assert model.rowCount() == 2
    assert model._messages[0]["content"] == "🌐 Fetch Web Page: example.com/news"
    assert model._messages[0]["status"] == "done"
    assert model._messages[1]["status"] == "typing"
    assert svc._active_streaming_row == 1
    assert svc._active_has_content is False
