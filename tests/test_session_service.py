"""Tests for SessionService and SessionListModel."""

from __future__ import annotations

import sys
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


from app.backend.session import SessionListModel, SessionService
from app.backend.asyncio_runner import AsyncioRunner
from bao.session.manager import SessionManager


# ── SessionListModel tests ────────────────────────────────────────────────────


def test_model_empty_initially():
    m = SessionListModel()
    assert m.rowCount() == 0


def test_model_reset_sessions():
    m = SessionListModel()
    sessions = [
        {"key": "desktop:local::s1", "title": "Session 1", "updated_at": 100},
        {"key": "desktop:local::s2", "title": "Session 2", "updated_at": 200},
    ]
    m.reset_sessions(sessions, "desktop:local::s1")
    assert m.rowCount() == 2


def test_model_data_roles():
    from PySide6.QtCore import Qt, QModelIndex

    m = SessionListModel()
    sessions = [{"key": "k1", "title": "T1", "updated_at": 42}]
    m.reset_sessions(sessions, "k1")
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 1) == "k1"  # key
    assert m.data(idx, Qt.UserRole + 2) == "T1"  # title
    assert m.data(idx, Qt.UserRole + 3) is True  # isActive
    assert m.data(idx, Qt.UserRole + 4) == 42  # updatedAt


def test_model_inactive_session():
    from PySide6.QtCore import Qt

    m = SessionListModel()
    sessions = [{"key": "k1", "title": "T1", "updated_at": 0}]
    m.reset_sessions(sessions, "k2")  # k2 is active, not k1
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 3) is False


def test_model_set_active():
    from PySide6.QtCore import Qt

    m = SessionListModel()
    sessions = [
        {"key": "k1", "title": "T1", "updated_at": 0},
        {"key": "k2", "title": "T2", "updated_at": 0},
    ]
    m.reset_sessions(sessions, "k1")
    m.set_active("k2")
    assert m.data(m.index(0), Qt.UserRole + 3) is False
    assert m.data(m.index(1), Qt.UserRole + 3) is True


def test_model_invalid_index_returns_none():
    from PySide6.QtCore import Qt

    m = SessionListModel()
    idx = m.index(99)
    assert m.data(idx, Qt.UserRole + 1) is None


# ── SessionService tests ──────────────────────────────────────────────────────


def _make_mock_session_manager(sessions=None, active_key="", fail_delete=False):
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
        if fail_delete:
            raise RuntimeError("delete failed")
        nonlocal state_sessions
        state_sessions = [s for s in state_sessions if s["key"] != key]

    sm.set_active_session_key.side_effect = _set_active
    sm.clear_active_session_key.side_effect = _clear_active
    sm.delete_session.side_effect = _delete_session
    return sm


def test_service_initial_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
        assert svc.activeKey == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_refresh_populates_model():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )
        svc.initialize(sm)

        # Wait for async refresh to complete
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.sessionsModel.rowCount() == 1
        assert svc.activeKey == ""
        from PySide6.QtCore import Qt

        idx = svc.sessionsModel.index(0)
        assert svc.sessionsModel.data(idx, Qt.UserRole + 3) is False
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_gateway_ready_restores_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
        sm = _make_mock_session_manager(
            sessions=[{"key": "desktop:local::s1", "title": "Chat 1"}],
            active_key="desktop:local::s1",
        )

        svc.initialize(sm)

        from PySide6.QtCore import QEventLoop, QTimer

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
        from PySide6.QtCore import Qt

        idx = svc.sessionsModel.index(0)
        assert svc.sessionsModel.data(idx, Qt.UserRole + 3) is True
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_select_session_updates_active_key():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1"},
                {"key": "desktop:local::s2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.initialize(sm)

        from PySide6.QtCore import QEventLoop, QTimer

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
        svc = SessionService(runner)
        sm = _make_mock_session_manager(
            sessions=[
                {"key": "desktop:local::s1", "title": "Chat 1"},
                {"key": "desktop:local::s2", "title": "Chat 2"},
            ],
            active_key="desktop:local::s1",
        )
        svc.setGatewayReady()
        svc.initialize(sm)

        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        assert svc.sessionsModel.rowCount() == 2

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert svc.sessionsModel.rowCount() == 1
        assert svc.activeKey == "desktop:local::s2"

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.sessionsModel.rowCount() == 1
        assert svc.activeKey == "desktop:local::s2"
        assert ("desktop:local::s1", True) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_delete_session_persists_in_storage(tmp_path):
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
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

        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(400, loop.quit)
        loop.exec()

        assert svc.sessionsModel.rowCount() == 2

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
        svc = SessionService(runner)
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

        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()

        events = []
        svc.deleteCompleted.connect(lambda key, ok, _err: events.append((key, ok)))

        svc.deleteSession("desktop:local::s1")
        assert svc.sessionsModel.rowCount() == 1

        loop2 = QEventLoop()
        QTimer.singleShot(300, loop2.quit)
        loop2.exec()

        assert svc.sessionsModel.rowCount() == 2
        assert svc.activeKey == "desktop:local::s1"
        assert ("desktop:local::s1", False) in events
    finally:
        runner.shutdown(grace_s=1.0)


def test_service_refresh_without_manager_is_noop():
    runner = AsyncioRunner()
    runner.start()
    try:
        svc = SessionService(runner)
        svc.refresh()  # should not raise
        assert svc.sessionsModel.rowCount() == 0
    finally:
        runner.shutdown(grace_s=1.0)
