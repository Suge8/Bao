"""Tests for SessionService and SessionListModel."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from app.backend.asyncio_runner import AsyncioRunner
from bao.session.manager import SessionManager

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
    sessions = [{"key": "k1", "title": "T1", "updated_at": 42}]
    m.reset_sessions(sessions, "k1")
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 1) == "k1"  # key
    assert m.data(idx, Qt.UserRole + 2) == "T1"  # title
    assert m.data(idx, Qt.UserRole + 3) is True  # isActive
    assert m.data(idx, Qt.UserRole + 4) == 42  # updatedAt


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


# ── SessionService tests ──────────────────────────────────────────────────────


def _make_mock_session_manager(
    sessions=None,
    active_key="",
    fail_delete=False,
    delete_returns_false=False,
    delete_returns_false_after_delete=False,
):
    sm = MagicMock()
    if sessions is None:
        sessions = []
    state = {"active": active_key}

    state_sessions = [
        {
            "key": s["key"],
            "updated_at": s.get("updated_at", 0),
            "metadata": {"title": s.get("title", s["key"])},
        }
        for s in sessions
    ]

    def _list_sessions():
        return [
            {
                "key": s["key"],
                "updated_at": s.get("updated_at", 0),
                "metadata": dict(s.get("metadata", {})),
            }
            for s in state_sessions
        ]

    sm.list_sessions.side_effect = _list_sessions
    sm.get_active_session_key.side_effect = lambda _natural_key: state["active"]

    def _set_active(_natural_key, key):
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

    sm.set_active_session_key.side_effect = _set_active
    sm.clear_active_session_key.side_effect = _clear_active
    sm.delete_session.side_effect = _delete_session
    return sm


def test_service_initial_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = _new_session_service(runner)
        assert svc.activeKey == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_shutdown_stops_unread_timer():
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

        assert svc._unread_timer.isActive() is True
        svc.shutdown()
        assert svc._unread_timer.isActive() is False
        svc.refresh()
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
        assert svc.activeKey == "desktop:local::s3"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.activeKey == "desktop:local::s3"
        assert sm.get_active_session_key("desktop:local") == "desktop:local::s3"
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

        async def _delayed_delete(key: str, new_active: str) -> None:
            await asyncio.sleep(0.15)
            await original_delete(key, new_active)

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
        svc._model.reset_sessions([sessions_before[2]], "desktop:local::s3", {"desktop:local::s3"})
        svc._pending_deletes = {
            "desktop:local::s1": (
                sessions_before,
                "desktop:local::s1",
                "desktop:local::s3",
                {"desktop:local::s2"},
            ),
            "desktop:local::s2": (
                sessions_before,
                "desktop:local::s2",
                "desktop:local::s3",
                {"desktop:local::s2"},
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
        svc._model.reset_sessions(sessions, "desktop:local::s1", {"desktop:local::s2"})

        svc.deleteSession("desktop:local::s1")

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        idx_s2 = _sessions_model(svc).index(1)
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
    loaded.metadata["desktop_last_read_at"] = datetime.now().isoformat()
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
    sm._meta_tbl.add(
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
