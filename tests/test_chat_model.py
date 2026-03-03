"""Tests for ChatMessageModel."""

from __future__ import annotations

import importlib
import sys

pytest = importlib.import_module("pytest")

QtGui = pytest.importorskip("PySide6.QtGui")
QtCore = pytest.importorskip("PySide6.QtCore")
QGuiApplication = QtGui.QGuiApplication
Qt = QtCore.Qt


# Need a QGuiApplication instance for Qt models
@pytest.fixture(scope="session")
def qapp():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _new_model():
    from app.backend.chat import ChatMessageModel

    return ChatMessageModel()


def test_append_user(qapp):
    m = _new_model()
    row = m.append_user("hello")
    assert row == 0
    assert m.rowCount() == 1
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 2) == "user"
    assert m.data(idx, Qt.UserRole + 3) == "hello"


def test_append_assistant(qapp):
    m = _new_model()
    row = m.append_assistant("hi there")
    assert row == 0
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 2) == "assistant"
    assert m.data(idx, Qt.UserRole + 4) == "markdown"
    assert m.data(idx, Qt.UserRole + 5) == "typing"


def test_update_content(qapp):
    m = _new_model()
    row = m.append_assistant("")
    m.update_content(row, "partial")
    idx = m.index(row)
    assert m.data(idx, Qt.UserRole + 3) == "partial"


def test_set_status(qapp):
    m = _new_model()
    row = m.append_assistant("done text", status="typing")
    m.set_status(row, "done")
    idx = m.index(row)
    assert m.data(idx, Qt.UserRole + 5) == "done"


def test_datachanged_only_one_row(qapp):
    m = _new_model()
    m.append_user("a")
    row = m.append_assistant("")
    m.append_user("b")

    changed_rows = []

    def on_changed(top, bottom, roles):
        changed_rows.append((top.row(), bottom.row()))

    m.dataChanged.connect(on_changed)
    m.update_content(row, "new content")
    assert changed_rows == [(row, row)]


def test_large_append(qapp):
    """1000 appends should complete quickly."""
    import time

    m = _new_model()
    start = time.time()
    for i in range(1000):
        m.append_user(f"message {i}")
    elapsed = time.time() - start
    assert m.rowCount() == 1000
    assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s"


def test_clear(qapp):
    m = _new_model()
    for i in range(5):
        m.append_user(f"msg {i}")
    m.clear()
    assert m.rowCount() == 0


def test_role_names(qapp):
    m = _new_model()
    names = m.roleNames()
    values = list(names.values())
    assert b"content" in values
    assert b"role" in values
    assert b"status" in values


def test_load_history_source_renders_as_system(qapp):
    """Messages with _source metadata should render as system bubbles, not user."""
    m = _new_model()
    m.load_history(
        [
            {"role": "user", "content": "[System: subagent] task done", "_source": "subagent"},
            {"role": "assistant", "content": "summary"},
            {"role": "user", "content": "[System: cron] scheduled", "_source": "cron"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "normal user msg"},
        ]
    )
    assert m.rowCount() == 5
    # subagent message → system bubble
    assert m.data(m.index(0), Qt.UserRole + 2) == "system"
    # assistant stays assistant
    assert m.data(m.index(1), Qt.UserRole + 2) == "assistant"
    # cron message → system bubble
    assert m.data(m.index(2), Qt.UserRole + 2) == "system"
    # assistant stays assistant
    assert m.data(m.index(3), Qt.UserRole + 2) == "assistant"
    # normal user message stays user
    assert m.data(m.index(4), Qt.UserRole + 2) == "user"


def test_load_prepared_skips_reset_when_render_equivalent(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    raw = [
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "world"},
    ]
    prepared = ChatMessageModel.prepare_history(raw)
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)
    m.load_prepared([dict(item) for item in prepared])

    assert len(resets) == 1


def test_load_prepared_skips_reset_when_only_entrance_flags_differ(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    row = m.append_assistant("hello", status="done", entrance_pending=True)
    m.mark_entrance_pending(row)
    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "hello", "status": "done"}]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)

    assert len(resets) == 0


def test_prepare_history_preserves_valid_status(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "assistant", "content": "a", "status": "error"},
            {"role": "system", "content": "s", "status": "typing"},
            {"role": "user", "content": "u", "_source": "cron", "status": "error"},
            {"role": "tool", "content": "t", "status": "typing"},
        ]
    )

    assert prepared[0]["status"] == "error"
    assert prepared[1]["status"] == "typing"
    assert prepared[2]["status"] == "error"
    assert prepared[3]["status"] == "typing"


def test_prepare_history_invalid_status_falls_back_done(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "assistant", "content": "a", "status": "bad"},
            {"role": "system", "content": "s", "status": 1},
            {"role": "user", "content": "u", "_source": "subagent", "status": None},
        ]
    )

    assert prepared[0]["status"] == "done"
    assert prepared[1]["status"] == "done"
    assert prepared[2]["status"] == "done"
