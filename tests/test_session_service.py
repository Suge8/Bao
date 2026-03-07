"""Tests for SessionService and SessionListModel."""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import json
import sys
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from app.backend.asyncio_runner import AsyncioRunner
from bao.session.manager import SessionChangeEvent, SessionManager

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication
Qt = QtCore.Qt
QModelIndex = QtCore.QModelIndex
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


_LIVE_SESSION_SERVICES: list[Any] = []


@pytest.fixture(autouse=True)
def cleanup_session_services(qt_app):
    yield
    while _LIVE_SESSION_SERVICES:
        svc = _LIVE_SESSION_SERVICES.pop()
        try:
            svc.shutdown()
        except Exception:
            pass
        try:
            svc.deleteLater()
        except Exception:
            pass
    qt_app.processEvents()


# ── SessionListModel tests ────────────────────────────────────────────────────


def _session_classes():
    from app.backend.session import SessionListModel, SessionService

    return SessionListModel, SessionService


def _new_session_model():
    session_list_model_cls, _ = _session_classes()
    return session_list_model_cls()


def _new_session_service(runner: AsyncioRunner):
    _, session_service_cls = _session_classes()
    svc = session_service_cls(runner)
    _LIVE_SESSION_SERVICES.append(svc)
    return svc


def _sessions_model(svc: Any) -> Any:
    return svc.sessionsModel


def _index_by_key(svc: Any, key: str) -> Any:
    model = _sessions_model(svc)
    for i in range(model.rowCount()):
        idx = model.index(i)
        if model.data(idx, Qt.UserRole + 1) == key:
            return idx
    return QModelIndex()


def test_model_empty_initially():
    m = _new_session_model()
    assert m.rowCount() == 0


def test_model_reset_sessions():
    m = _new_session_model()
    sessions = [
        {"key": "desktop:local::s1", "title": "Session 1", "updated_at": 100},
        {"key": "desktop:local::s2", "title": "Session 2", "updated_at": 200},
    ]
    m.reset_sessions(sessions, "desktop:local::s1")
    assert m.rowCount() == 2


def test_model_data_roles():
    m = _new_session_model()
    sessions = [
        {
            "key": "k1",
            "title": "T1",
            "updated_at": 42,
            "updated_label": "<1m",
            "message_count": 0,
            "has_messages": False,
        }
    ]
    m.reset_sessions(sessions, "k1")
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 1) == "k1"  # key
    assert m.data(idx, Qt.UserRole + 2) == "T1"  # title
    assert m.data(idx, Qt.UserRole + 3) is True  # isActive
    assert m.data(idx, Qt.UserRole + 4) == 42  # updatedAt
    assert m.data(idx, Qt.UserRole + 7) == "<1m"
    assert m.data(idx, Qt.UserRole + 8) == 0
    assert m.data(idx, Qt.UserRole + 9) is False


def test_model_inactive_session():
    m = _new_session_model()
    sessions = [{"key": "k1", "title": "T1", "updated_at": 0}]
    m.reset_sessions(sessions, "k2")  # k2 is active, not k1
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 3) is False


def test_model_set_active():
    m = _new_session_model()
    sessions = [
        {"key": "k1", "title": "T1", "updated_at": 0},
        {"key": "k2", "title": "T2", "updated_at": 0},
    ]
    m.reset_sessions(sessions, "k1")
    m.set_active("k2")
    assert m.data(m.index(0), Qt.UserRole + 3) is False
    assert m.data(m.index(1), Qt.UserRole + 3) is True


def test_model_invalid_index_returns_none():
    m = _new_session_model()
    idx = m.index(99)
    assert m.data(idx, Qt.UserRole + 1) is None


def test_format_display_title_for_desktop_default_key():
    from app.backend.session import _format_display_title

    assert _format_display_title("desktop:local", None) == "default"


def test_format_display_title_uses_named_session_suffix():
    from app.backend.session import _format_display_title

    assert _format_display_title("desktop:local::planning", "") == "planning"


def test_format_updated_label_uses_compact_relative_units():
    from app.backend.session import _format_updated_label

    assert _format_updated_label(datetime.now().isoformat()) == "<1m"
    assert (
        _format_updated_label((datetime.now() - timedelta(hours=1, minutes=5)).isoformat()) == "1h"
    )


# ── SessionService tests ──────────────────────────────────────────────────────


def _make_mock_session_manager(
    sessions=None,
    active_key="",
    fail_delete=False,
    delete_returns_false=False,
    delete_returns_false_after_delete=False,
    fail_set_active=False,
):
    sm = MagicMock()
    listeners: list[Any] = []
    if sessions is None:
        sessions = []
    state = {"active": active_key}

    state_sessions = [
        {
            "key": s["key"],
            "updated_at": s.get("updated_at", 0),
            "metadata": {"title": s.get("title", s["key"]), **dict(s.get("metadata", {}))},
            "message_count": s.get("message_count"),
            "has_messages": s.get("has_messages"),
        }
        for s in sessions
    ]

    def _list_sessions():
        return [
            {
                "key": s["key"],
                "updated_at": s.get("updated_at", 0),
                "metadata": dict(s.get("metadata", {})),
                "message_count": s.get("message_count"),
                "has_messages": s.get("has_messages"),
            }
            for s in state_sessions
        ]

    sm.list_sessions.side_effect = _list_sessions
    sm.get_active_session_key.side_effect = lambda _natural_key: state["active"]

    def _set_active(_natural_key, key):
        if fail_set_active:
            raise RuntimeError("set active failed")
        state["active"] = key

    def _clear_active(_natural_key):
        state["active"] = ""

    def _delete_session(key):
        nonlocal state_sessions
        if fail_delete:
            raise RuntimeError("delete failed")
        if delete_returns_false_after_delete:
            state_sessions = [s for s in state_sessions if s["key"] != key]
            return False
        if delete_returns_false:
            return False
        state_sessions = [s for s in state_sessions if s["key"] != key]
        return True

    def _get_or_create(key):
        session = MagicMock()
        session.key = key
        session.metadata = {}
        session.messages = []
        session.created_at = datetime.now()
        session.updated_at = datetime.now()
        return session

    def _save(session):
        nonlocal state_sessions
        key = str(getattr(session, "key", ""))
        if not key:
            return
        updated_at = getattr(session, "updated_at", datetime.now())
        updated_value = (
            updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)
        )
        metadata = dict(getattr(session, "metadata", {}))
        existing = next((s for s in state_sessions if s["key"] == key), None)
        if existing is None:
            state_sessions.append(
                {
                    "key": key,
                    "updated_at": updated_value,
                    "metadata": metadata,
                }
            )
            return
        existing["updated_at"] = updated_value
        existing["metadata"] = metadata

    sm.set_active_session_key.side_effect = _set_active
    sm.clear_active_session_key.side_effect = _clear_active
    sm.delete_session.side_effect = _delete_session
    sm.get_or_create.side_effect = _get_or_create
    sm.save.side_effect = _save
    sm.add_change_listener.side_effect = listeners.append

    def _remove_change_listener(listener):
        if listener in listeners:
            listeners.remove(listener)

    def _emit_change(session_key: str, kind: str) -> None:
        event = SessionChangeEvent(session_key=session_key, kind=kind)
        for listener in list(listeners):
            listener(event)

    sm.remove_change_listener.side_effect = _remove_change_listener
    sm._listeners = listeners
    sm._emit_change = _emit_change
    return sm


def test_service_initial_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        assert svc.activeKey == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_shutdown_clears_runtime_state():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.shutdown()
        assert svc._disposed is True
        assert svc._session_manager is None
        svc.refresh()
    finally:
        runner.shutdown(grace_s=1.0)


def test_done_callbacks_ignore_cancelled_future():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        future = concurrent.futures.Future()
        future.cancel()

        svc._on_list_done(future)
        svc._on_select_done(future)
        svc._on_sync_family_active_done(future)
        svc._on_create_done("desktop:local::new", future)
        svc._on_delete_done("desktop:local::old", future)
    finally:
        runner.shutdown(grace_s=1.0)


def test_initialize_registers_and_shutdown_removes_change_listener():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager()

        svc.initialize(sm)

        assert svc._on_session_change in sm._listeners

        svc.shutdown()

        assert svc._on_session_change not in sm._listeners
    finally:
        runner.shutdown(grace_s=1.0)


def test_bootstrap_workspace_initializes_session_manager_async(qt_app, tmp_path):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager()
        ready: list[Any] = []
        svc.sessionManagerReady.connect(ready.append)

        with patch("bao.session.manager.SessionManager", return_value=sm):
            svc.bootstrapWorkspace(str(tmp_path / "workspace"))
            assert svc.sessionsLoading is True
            loop = QEventLoop()
            QTimer.singleShot(300, loop.quit)
            loop.exec()

        assert svc._session_manager is sm
        assert ready == [sm]
        assert svc.sessionsLoading is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_bootstrap_result_does_not_override_existing_session_manager(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        current = _make_mock_session_manager()
        late = _make_mock_session_manager()
        ready: list[Any] = []
        svc.sessionManagerReady.connect(ready.append)

        svc.initialize(current)
        svc._handle_bootstrap_result(True, "", late)
        qt_app.processEvents()

        assert svc._session_manager is current
        assert ready == []
    finally:
        runner.shutdown(grace_s=1.0)


def test_bootstrap_done_ignores_cancelled_future() -> None:
    import concurrent.futures

    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        fut: concurrent.futures.Future[object] = concurrent.futures.Future()
        fut.cancel()

        svc._on_bootstrap_done(fut)

        assert svc._session_manager is None
    finally:
        runner.shutdown(grace_s=1.0)


def test_session_change_event_refreshes_session_list(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(sessions=[{"key": "desktop:local", "title": "default"}])
        svc.setGatewayReady()
        svc.initialize(sm)
        qt_app.processEvents()

        sm.list_sessions.side_effect = lambda: [
            {"key": "desktop:local", "updated_at": "1", "metadata": {}},
            {"key": "telegram:123", "updated_at": "2", "metadata": {}},
        ]

        sm._emit_change("telegram:123", "messages")
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 2
    finally:
        runner.shutdown(grace_s=1.0)


def test_refresh_exposes_sessions_loading_state(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc._session_manager = object()

        async def _slow_list(seq: int):
            await asyncio.sleep(0.05)
            return seq, [], ""

        loading_events: list[bool] = []
        svc.sessionsLoadingChanged.connect(loading_events.append)

        with patch.object(svc, "_list_sessions", side_effect=_slow_list):
            svc.refresh()
            assert svc.sessionsLoading is True

            loop = QEventLoop()
            QTimer.singleShot(200, loop.quit)
            loop.exec()

        assert svc.sessionsLoading is False
        assert loading_events[0] is True
        assert loading_events[-1] is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_set_local_active_key_clears_unread_for_selected_session(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc._model.reset_sessions(
            [
                {
                    "key": "desktop:local::default",
                    "title": "default",
                    "is_active": False,
                    "updated_at": "",
                    "channel": "desktop",
                    "has_unread": False,
                    "updated_label": "",
                },
                {
                    "key": "telegram:room1",
                    "title": "room1",
                    "is_active": False,
                    "updated_at": "",
                    "channel": "telegram",
                    "has_unread": True,
                    "updated_label": "",
                },
            ],
            "",
        )

        svc._set_local_active_key("telegram:room1")
        svc._set_local_active_key("desktop:local::default")

        unread_role = int(Qt.ItemDataRole.UserRole) + 6
        telegram_index = svc._model.index(1, 0)
        assert svc._model.data(telegram_index, unread_role) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_session_change_event_ignores_after_shutdown(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(sessions=[{"key": "desktop:local", "title": "default"}])
        svc.initialize(sm)
        qt_app.processEvents()

        svc.shutdown()
        sm._emit_change("desktop:local", "messages")
        qt_app.processEvents()

        assert svc.activeKey == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_result_triggers_background_display_tail_backfill(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = MagicMock()
        svc._session_manager = sm
        sessions = [
            {"key": "desktop:local::s1", "title": "One", "updated_at": 1, "channel": "desktop"},
            {"key": "desktop:local::s2", "title": "Two", "updated_at": 2, "channel": "desktop"},
        ]

        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s1"))

        loop = QEventLoop()
        QTimer.singleShot(250, loop.quit)
        loop.exec()

        sm.backfill_display_tail_rows.assert_called_once_with(
            ["desktop:local::s1", "desktop:local::s2"], 200
        )
    finally:
        runner.shutdown(grace_s=1.0)


def test_active_summary_changed_emits_current_session_summary(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()
        summaries: list[tuple[str, object, object]] = []
        svc.activeSummaryChanged.connect(
            lambda key, count, has_messages: summaries.append((key, count, has_messages))
        )

        svc._handle_list_result(
            True,
            "",
            (
                [
                    {
                        "key": "desktop:local::empty",
                        "title": "Empty",
                        "updated_at": 1,
                        "channel": "desktop",
                        "message_count": 0,
                        "has_messages": False,
                    }
                ],
                "desktop:local::empty",
            ),
        )

        assert summaries[-1] == ("desktop:local::empty", 0, False)
    finally:
        runner.shutdown(grace_s=1.0)


def test_initialize_syncs_external_family_active_key(tmp_path, qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = SessionManager(tmp_path)
        sm.save(sm.get_or_create("telegram:chat"))
        sm.save(sm.get_or_create("telegram:chat::s2"))
        sm.set_active_session_key("desktop:local", "telegram:chat::s2")

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert sm.get_active_session_key("telegram:chat") == "telegram:chat::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_external_family_active_sync_keeps_active_chat_realtime(tmp_path, qt_app):
    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import ChatService

    runner = AsyncioRunner()
    runner.start()
    chat = None
    try:
        svc = _new_session_service(runner)
        model = ChatMessageModel()
        chat = ChatService(model, runner)
        sm = SessionManager(tmp_path)
        sm.save(sm.get_or_create("telegram:chat"))
        sm.save(sm.get_or_create("telegram:chat::s2"))
        sm.set_active_session_key("desktop:local", "telegram:chat::s2")

        svc.activeKeyChanged.connect(chat.setSessionKey)
        chat.setSessionManager(sm)
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        async def _inbound_like_core() -> None:
            natural = "telegram:chat"
            key = sm.get_active_session_key(natural) or natural
            session = sm.get_or_create(key)
            session.add_message("user", "incoming external")
            sm.save(session)

        runner.submit(_inbound_like_core()).result(timeout=2)

        deadline = datetime.now() + timedelta(seconds=1)
        while model.rowCount() == 0 and datetime.now() < deadline:
            loop2 = QEventLoop()
            QTimer.singleShot(50, loop2.quit)
            loop2.exec()

        assert model.rowCount() == 1
        assert model._messages[-1]["content"] == "incoming external"
    finally:
        if chat is not None:
            try:
                chat.deleteLater()
            except Exception:
                pass
        runner.shutdown(grace_s=1.0)


def test_rapid_same_family_selection_persists_latest_active_key(tmp_path, qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = SessionManager(tmp_path)
        sm.save(sm.get_or_create("telegram:chat::s1"))
        sm.save(sm.get_or_create("telegram:chat::s2"))

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.selectSession("telegram:chat::s1")
        svc.selectSession("telegram:chat::s2")

        loop2 = QEventLoop()
        QTimer.singleShot(400, loop2.quit)
        loop2.exec()

        assert sm.get_active_session_key("desktop:local") == "telegram:chat::s2"
        assert sm.get_active_session_key("telegram:chat") == "telegram:chat::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_metadata_change_event_refreshes_session_list_for_plan_updates(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(sessions=[{"key": "desktop:local", "title": "default"}])
        svc.setGatewayReady()
        svc.initialize(sm)
        qt_app.processEvents()

        sm.list_sessions.side_effect = lambda: [
            {
                "key": "desktop:local",
                "updated_at": "2",
                "metadata": {"title": "default", "_plan_state": {"goal": "ship"}},
            }
        ]

        sm._emit_change("desktop:local", "metadata")
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 1) == "desktop:local"
    finally:
        runner.shutdown(grace_s=1.0)


def test_session_service_labels_cron_and_heartbeat_channels(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "heartbeat", "title": "heartbeat", "updated_at": "1"},
                {"key": "cron:job-1", "title": "cron", "updated_at": "2"},
            ]
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        heartbeat_idx = _index_by_key(svc, "heartbeat")
        cron_idx = _index_by_key(svc, "cron:job-1")
        assert _sessions_model(svc).data(heartbeat_idx, Qt.UserRole + 5) == "heartbeat"
        assert _sessions_model(svc).data(cron_idx, Qt.UserRole + 5) == "cron"
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_refresh_populates_model():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 1
        assert svc.activeKey == ""
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 3) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_gateway_ready_restores_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )

        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.activeKey == ""

        svc.setGatewayReady()
        svc.refresh()

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.activeKey == "desktop:local::s1"
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 3) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_gateway_ready_prefers_persisted_active_key_over_latest_session():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1},
                {"key": "desktop:local::s2", "title": "Chat 2", "updated_at": 2},
            ],
            active_key="desktop:local::s1",
        )

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.activeKey == "desktop:local::s1"
        assert _sessions_model(svc).data(_sessions_model(svc).index(0), Qt.UserRole + 3) is True
        assert _sessions_model(svc).data(_sessions_model(svc).index(1), Qt.UserRole + 3) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_gateway_ready_autopick_persists_selected_session():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1},
                {"key": "desktop:local::s2", "title": "Chat 2", "updated_at": 2},
            ],
            active_key="",
        )

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.activeKey == "desktop:local::s2"
        assert sm.get_active_session_key("desktop:local") == "desktop:local::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_prefers_valid_persisted_active_when_local_active_is_stale():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()
        svc._active_key = "desktop:local::stale"
        svc._last_emitted_active_key = "desktop:local::stale"

        sessions = [
            {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1, "channel": "desktop"},
            {"key": "desktop:local::s2", "title": "Chat 2", "updated_at": 2, "channel": "desktop"},
        ]

        active_keys: list[str] = []
        svc.activeKeyChanged.connect(active_keys.append)

        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s1"))

        assert svc.activeKey == "desktop:local::s1"
        assert active_keys == ["desktop:local::s1"]
        assert _sessions_model(svc).data(_sessions_model(svc).index(0), Qt.UserRole + 3) is True
        assert _sessions_model(svc).data(_sessions_model(svc).index(1), Qt.UserRole + 3) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_gateway_ready_repairs_invalid_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::missing",
        )

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.activeKey == "desktop:local::s1"
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_select_session_updates_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1"},
                {"key": "desktop:local::s2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        keys = []
        svc.activeKeyChanged.connect(keys.append)
        svc.selectSession("desktop:local::s2")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert "desktop:local::s2" in keys

        svc.refresh()
        loop3 = QEventLoop()
        QTimer.singleShot(300, loop3.quit)
        loop3.exec()

        assert svc.activeKey == "desktop:local::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_does_not_override_pending_selection():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        sessions = [
            {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1, "channel": "desktop"},
            {"key": "desktop:local::s2", "title": "Chat 2", "updated_at": 2, "channel": "desktop"},
        ]
        svc._active_key = "desktop:local::s1"
        svc._pending_select_key = "desktop:local::s2"

        svc._handle_list_result(True, "", (sessions, "desktop:local::s1"))

        assert svc.activeKey == "desktop:local::s2"
        idx = _sessions_model(svc).index(1)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 3) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_active_only_change_keeps_local_active_source_of_truth():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        sessions = [
            {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1, "channel": "desktop"},
            {"key": "desktop:local::s2", "title": "Chat 2", "updated_at": 2, "channel": "desktop"},
        ]

        svc._active_key = "desktop:local::s1"
        svc._last_emitted_active_key = "desktop:local::s1"
        svc._model.reset_sessions([dict(s) for s in sessions], "desktop:local::s1")

        changed_events: list[bool] = []
        active_keys: list[str] = []
        svc.sessionsChanged.connect(lambda: changed_events.append(True))
        svc.activeKeyChanged.connect(active_keys.append)

        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s1"))
        assert len(changed_events) == 1

        svc._pending_select_key = "desktop:local::s2"
        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s2"))
        assert len(changed_events) == 2
        assert svc.activeKey == "desktop:local::s2"
        assert active_keys == ["desktop:local::s2"]
        assert _sessions_model(svc).data(_sessions_model(svc).index(0), Qt.UserRole + 3) is False
        assert _sessions_model(svc).data(_sessions_model(svc).index(1), Qt.UserRole + 3) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_updates_visible_time_fields_even_when_keys_match():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        sessions = [
            {
                "key": "desktop:local::s1",
                "title": "Chat 1",
                "updated_at": 1,
                "updated_label": "<1m",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "desktop:local::s2",
                "title": "Chat 2",
                "updated_at": 2,
                "updated_label": "2m",
                "channel": "desktop",
                "has_unread": False,
            },
        ]

        svc._active_key = "desktop:local::s1"
        svc._last_emitted_active_key = "desktop:local::s1"
        svc._model.reset_sessions([dict(s) for s in sessions], "desktop:local::s1")
        changed_events: list[bool] = []
        svc.sessionsChanged.connect(lambda: changed_events.append(True))

        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s1"))

        refreshed = [dict(s) for s in sessions]
        refreshed[0]["updated_at"] = 3
        refreshed[0]["updated_label"] = "3m"
        svc._handle_list_result(True, "", (refreshed, "desktop:local::s1"))

        idx = _sessions_model(svc).index(0)
        assert len(changed_events) == 2
        assert _sessions_model(svc).data(idx, Qt.UserRole + 7) == "3m"
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_uses_incoming_order_when_keys_unchanged():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        initial = [
            {
                "key": "desktop:local::s1",
                "title": "Chat 1",
                "updated_at": 10,
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "desktop:local::s2",
                "title": "Chat 2",
                "updated_at": 9,
                "channel": "desktop",
                "has_unread": False,
            },
        ]
        svc._handle_list_result(True, "", ([dict(s) for s in initial], "desktop:local::s1"))

        reordered = [
            {
                "key": "desktop:local::s2",
                "title": "Chat 2",
                "updated_at": 20,
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "desktop:local::s1",
                "title": "Chat 1",
                "updated_at": 10,
                "channel": "desktop",
                "has_unread": False,
            },
        ]
        svc._handle_list_result(True, "", ([dict(s) for s in reordered], "desktop:local::s1"))

        assert (
            _sessions_model(svc).data(_sessions_model(svc).index(0), Qt.UserRole + 1)
            == "desktop:local::s2"
        )
        assert (
            _sessions_model(svc).data(_sessions_model(svc).index(1), Qt.UserRole + 1)
            == "desktop:local::s1"
        )
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_emits_active_cleared_when_sessions_empty():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        sessions = [
            {"key": "desktop:local::s1", "title": "Chat 1", "updated_at": 1, "channel": "desktop"},
        ]
        active_keys: list[str] = []
        svc.activeKeyChanged.connect(active_keys.append)

        svc._handle_list_result(True, "", ([dict(s) for s in sessions], "desktop:local::s1"))
        assert svc.activeKey == "desktop:local::s1"

        svc._handle_list_result(True, "", ([], "desktop:local::s1"))
        assert _sessions_model(svc).rowCount() == 0
        assert svc.activeKey == ""
        assert active_keys[-1] == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_refresh_autocreates_session_when_empty_and_manager_present():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(sessions=[], active_key="")
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 1
        assert str(svc.activeKey).startswith("desktop:local::session-")
    finally:
        runner.shutdown(grace_s=1.0)


def test_unread_reappears_after_new_update_even_if_previously_cleared():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.setGatewayReady()

        sessions = [
            {
                "key": "desktop:local::s1",
                "title": "Chat 1",
                "updated_at": "2026-01-01T00:00:00",
                "channel": "desktop",
            },
            {
                "key": "desktop:local::s2",
                "title": "Chat 2",
                "updated_at": "2026-01-01T00:00:00",
                "channel": "desktop",
            },
        ]

        svc._model.reset_sessions([dict(s) for s in sessions], "desktop:local::s1")
        svc._active_key = "desktop:local::s1"

        refreshed: list[dict[str, Any]] = [dict(s) for s in sessions]
        refreshed[1]["has_unread"] = True
        svc._handle_list_result(
            True,
            "",
            (refreshed, "desktop:local::s1"),
        )

        idx_s2 = _sessions_model(svc).index(1)
        assert _sessions_model(svc).data(idx_s2, Qt.UserRole + 6) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_list_sessions_unread_uses_ai_timestamps_only():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {
                    "key": "desktop:local::s1",
                    "title": "Chat 1",
                    "updated_at": "2026-01-01T00:10:00",
                    "metadata": {
                        "desktop_last_ai_at": "2026-01-01T00:09:00",
                        "desktop_last_seen_ai_at": "2026-01-01T00:08:00",
                    },
                },
                {
                    "key": "desktop:local::s2",
                    "title": "Chat 2",
                    "updated_at": "2026-01-01T00:11:00",
                    "metadata": {
                        "desktop_last_ai_at": "2026-01-01T00:07:00",
                        "desktop_last_seen_ai_at": "2026-01-01T00:07:00",
                    },
                },
                {
                    "key": "desktop:local::s3",
                    "title": "Chat 3",
                    "updated_at": "2026-01-01T00:12:00",
                    "metadata": {
                        "desktop_last_seen_ai_at": "2026-01-01T00:06:00",
                    },
                },
            ],
            active_key="desktop:local::s2",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        idx_s1 = _index_by_key(svc, "desktop:local::s1")
        idx_s2 = _index_by_key(svc, "desktop:local::s2")
        idx_s3 = _index_by_key(svc, "desktop:local::s3")
        assert idx_s1.isValid()
        assert idx_s2.isValid()
        assert idx_s3.isValid()
        assert _sessions_model(svc).data(idx_s1, Qt.UserRole + 6) is True
        assert _sessions_model(svc).data(idx_s2, Qt.UserRole + 6) is False
        assert _sessions_model(svc).data(idx_s3, Qt.UserRole + 6) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_select_session_does_not_mark_seen_ai_in_session_service():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.selectSession("desktop:local::s2")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert sm.update_metadata_only.call_count == 0
    finally:
        runner.shutdown(grace_s=1.0)


def test_new_session_sets_active_key_before_list_refresh():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        emitted_keys: list[str] = []
        svc.activeKeyChanged.connect(emitted_keys.append)

        svc.newSession("")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert str(svc.activeKey).startswith("desktop:local::session-")
        assert any(key.startswith("desktop:local::session-") for key in emitted_keys)
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_session_updates_model():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 2

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert _sessions_model(svc).rowCount() == 1
        assert svc.activeKey == "desktop:local::s2"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        assert svc.activeKey == "desktop:local::s2"
        assert ("desktop:local::s1", True) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_session_persists_in_storage(tmp_path):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = SessionManager(tmp_path)
        s1 = sm.get_or_create("desktop:local::s1")
        s1.add_message("user", "hello")
        sm.save(s1)
        s2 = sm.get_or_create("desktop:local::s2")
        s2.add_message("user", "world")
        sm.save(s2)
        sm.set_active_session_key("desktop:local", "desktop:local::s1")

        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(400, loop.quit)
        loop.exec()

        assert _sessions_model(svc).rowCount() == 2

        svc.deleteSession("desktop:local::s1")

        loop2 = QEventLoop()
        QTimer.singleShot(400, loop2.quit)
        loop2.exec()

        keys = [row["key"] for row in sm.list_sessions()]
        assert "desktop:local::s1" not in keys
        assert "desktop:local::s2" in keys
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_failure_restores_model():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
            fail_delete=True,
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert _sessions_model(svc).rowCount() == 1

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 2
        assert svc.activeKey == "desktop:local::s1"
        assert ("desktop:local::s1", False) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_false_result_restores_model():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
            delete_returns_false=True,
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert _sessions_model(svc).rowCount() == 1

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 2
        assert svc.activeKey == "desktop:local::s1"
        assert ("desktop:local::s1", False) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_false_after_delete_treated_as_success():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
            delete_returns_false_after_delete=True,
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert _sessions_model(svc).rowCount() == 1

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        assert svc.activeKey == "desktop:local::s2"
        assert ("desktop:local::s1", True) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_active_picks_adjacent_session_and_persists_active():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
                {"key": "desktop:local::s3", "title": "Chat 3"},
            ],
            active_key="desktop:local::s2",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.deleteSession("desktop:local::s2")
        assert _sessions_model(svc).rowCount() == 2
        assert svc.activeKey == "desktop:local::s1"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.activeKey == "desktop:local::s1"
        assert sm.get_active_session_key("desktop:local") == "desktop:local::s1"
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_non_active_keeps_active_stable():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.deleteSession("desktop:local::s2")
        assert _sessions_model(svc).rowCount() == 1
        assert svc.activeKey == "desktop:local::s1"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.activeKey == "desktop:local::s1"
        assert sm.get_active_session_key("desktop:local") == "desktop:local::s1"
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_active_prefers_same_channel_neighbor():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "telegram:chat::1", "title": "T1"},
                {"key": "desktop:local::s1", "title": "D1"},
                {"key": "telegram:chat::2", "title": "T2"},
                {"key": "desktop:local::s2", "title": "D2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.deleteSession("desktop:local::s1")
        assert svc.activeKey == "desktop:local::s2"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert sm.get_active_session_key("desktop:local") == "desktop:local::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_refresh_during_pending_delete_does_not_resurrect_session():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        original_delete = svc._delete_session

        async def _delayed_delete(key: str, new_active: str, seq: int | None) -> str:
            await asyncio.sleep(0.15)
            return await original_delete(key, new_active, seq)

        svc._delete_session = _delayed_delete

        svc.deleteSession("desktop:local::s1")
        assert _sessions_model(svc).rowCount() == 1

        svc.refresh()
        loop2 = QEventLoop()
        QTimer.singleShot(80, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 1) == "desktop:local::s2"

        loop3 = QEventLoop()
        QTimer.singleShot(300, loop3.quit)
        loop3.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx2 = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx2, Qt.UserRole + 1) == "desktop:local::s2"
    finally:
        runner.shutdown(grace_s=1.0)


def test_local_delete_ignores_followup_deleted_change_event(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        original_delete = sm.delete_session.side_effect

        def _delete_with_change(key: str) -> bool:
            assert callable(original_delete)
            result = bool(original_delete(key))
            sm._emit_change(key, "deleted")
            return result

        sm.delete_session.side_effect = _delete_with_change
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        sessions_changed_count = 0

        def _count_sessions_changed() -> None:
            nonlocal sessions_changed_count
            sessions_changed_count += 1

        svc.sessionsChanged.connect(_count_sessions_changed)

        svc.deleteSession("desktop:local::s1")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 1) == "desktop:local::s2"
        assert sessions_changed_count == 1
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_failure_rollback_respects_other_pending_deletes():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sessions_before = [
            {"key": "desktop:local::s1", "title": "S1", "channel": "desktop"},
            {"key": "desktop:local::s2", "title": "S2", "channel": "desktop"},
            {"key": "desktop:local::s3", "title": "S3", "channel": "desktop"},
        ]
        svc._active_key = "desktop:local::s3"
        svc._model.reset_sessions([sessions_before[2]], "desktop:local::s3")
        svc._pending_deletes = {
            "desktop:local::s1": (
                sessions_before,
                "desktop:local::s1",
                "desktop:local::s3",
            ),
            "desktop:local::s2": (
                sessions_before,
                "desktop:local::s2",
                "desktop:local::s3",
            ),
        }

        svc._handle_delete_result("desktop:local::s1", False, "delete failed")

        keys = [
            _sessions_model(svc).data(_sessions_model(svc).index(i), Qt.UserRole + 1)
            for i in range(_sessions_model(svc).rowCount())
        ]
        assert "desktop:local::s2" not in keys
        assert "desktop:local::s1" in keys
        assert "desktop:local::s3" in keys
    finally:
        runner.shutdown(grace_s=1.0)


def test_external_deleted_change_event_still_refreshes_visible_session(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        sm.list_sessions.side_effect = lambda: [
            {"key": "desktop:local::s1", "updated_at": "2", "metadata": {}},
        ]

        svc._handle_session_change(
            SessionChangeEvent(session_key="desktop:local::s2", kind="deleted")
        )

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 1) == "desktop:local::s1"
    finally:
        runner.shutdown(grace_s=1.0)


def test_delete_success_with_active_sync_failure_keeps_deleted_session_gone(qt_app):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
            fail_set_active=True,
        )
        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        svc.deleteSession("desktop:local::s1")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert _sessions_model(svc).rowCount() == 1
        idx = _sessions_model(svc).index(0)
        assert _sessions_model(svc).data(idx, Qt.UserRole + 1) == "desktop:local::s2"
        assert svc.activeKey == "desktop:local::s2"
        assert ("desktop:local::s1", True) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_failure_restores_unread_snapshot():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
            fail_delete=True,
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        sessions = [dict(s) for s in svc._model._sessions]
        for item in sessions:
            item["has_unread"] = str(item.get("key", "")) == "desktop:local::s2"
        svc._model.reset_sessions(sessions, "desktop:local::s1")

        svc.deleteSession("desktop:local::s1")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        idx_s2 = _index_by_key(svc, "desktop:local::s2")
        assert idx_s2.isValid()
        assert _sessions_model(svc).data(idx_s2, Qt.UserRole + 1) == "desktop:local::s2"
        assert _sessions_model(svc).data(idx_s2, Qt.UserRole + 6) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_session_manager_mark_read_does_not_reorder_by_accident(tmp_path):
    sm = SessionManager(tmp_path)

    old_ts = datetime(2024, 1, 1, 0, 0, 0)
    new_ts = datetime(2024, 1, 2, 0, 0, 0)

    s1 = sm.get_or_create("desktop:local::old")
    s1.updated_at = old_ts
    sm.save(s1)

    s2 = sm.get_or_create("desktop:local::new")
    s2.updated_at = new_ts
    sm.save(s2)

    sm.invalidate("desktop:local::old")
    loaded = sm.get_or_create("desktop:local::old")
    loaded.metadata["desktop_last_seen_ai_at"] = datetime.now().isoformat()
    sm.save(loaded)

    sessions = sm.list_sessions()
    assert sessions[0]["key"] == "desktop:local::new"
    old_row = next(s for s in sessions if s["key"] == "desktop:local::old")
    assert old_row["updated_at"] == old_ts.isoformat()


def test_session_manager_delete_clears_active_marker_for_deleted_session(tmp_path):
    sm = SessionManager(tmp_path)

    s1 = sm.get_or_create("telegram:chat::1")
    s1.add_message("user", "hello")
    sm.save(s1)
    s2 = sm.get_or_create("telegram:chat::2")
    s2.add_message("user", "world")
    sm.save(s2)
    sm.set_active_session_key("telegram:chat", "telegram:chat::1")

    assert sm.get_active_session_key("telegram:chat") == "telegram:chat::1"
    assert sm.delete_session("telegram:chat::1") is True
    assert sm.get_active_session_key("telegram:chat") is None


def test_session_manager_delete_rolls_back_when_message_delete_fails(tmp_path):
    sm = SessionManager(tmp_path)
    key = "desktop:local::rollback"

    session = sm.get_or_create(key)
    session.add_message("user", "hello")
    sm.save(session)

    with patch.object(sm._msg_tbl, "delete", side_effect=RuntimeError("boom")):
        assert sm.delete_session(key) is False

    keys = [row["key"] for row in sm.list_sessions()]
    assert key in keys

    sm.invalidate(key)
    loaded = sm.get_or_create(key)
    assert any(msg.get("content") == "hello" for msg in loaded.messages)


def test_session_manager_get_active_key_prefers_latest_marker(tmp_path):
    sm = SessionManager(tmp_path)
    marker = "_active:desktop:local"
    sm._meta_table().add(
        [
            {
                "session_key": marker,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "metadata_json": json.dumps({"active_key": "desktop:local::old"}),
                "last_consolidated": 0,
            },
            {
                "session_key": marker,
                "created_at": "2024-01-02T00:00:00",
                "updated_at": "2024-01-02T00:00:00",
                "metadata_json": json.dumps({"active_key": "desktop:local::new"}),
                "last_consolidated": 0,
            },
        ]
    )

    assert sm.get_active_session_key("desktop:local") == "desktop:local::new"


def test_service_refresh_without_manager_is_noop():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        svc.refresh()  # should not raise
        assert _sessions_model(svc).rowCount() == 0
    finally:
        runner.shutdown(grace_s=1.0)
