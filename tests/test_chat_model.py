"""Tests for ChatMessageModel."""

from __future__ import annotations

import pytest

from PySide6.QtGui import QGuiApplication
import sys


# Need a QGuiApplication instance for Qt models
@pytest.fixture(scope="session")
def qapp():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


from app.backend.chat import ChatMessageModel
from PySide6.QtCore import Qt


def test_append_user(qapp):
    m = ChatMessageModel()
    row = m.append_user("hello")
    assert row == 0
    assert m.rowCount() == 1
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 2) == "user"
    assert m.data(idx, Qt.UserRole + 3) == "hello"


def test_append_assistant(qapp):
    m = ChatMessageModel()
    row = m.append_assistant("hi there")
    assert row == 0
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 2) == "assistant"
    assert m.data(idx, Qt.UserRole + 4) == "markdown"
    assert m.data(idx, Qt.UserRole + 5) == "typing"


def test_update_content(qapp):
    m = ChatMessageModel()
    row = m.append_assistant("")
    m.update_content(row, "partial")
    idx = m.index(row)
    assert m.data(idx, Qt.UserRole + 3) == "partial"


def test_set_status(qapp):
    m = ChatMessageModel()
    row = m.append_assistant("done text", status="typing")
    m.set_status(row, "done")
    idx = m.index(row)
    assert m.data(idx, Qt.UserRole + 5) == "done"


def test_datachanged_only_one_row(qapp):
    m = ChatMessageModel()
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

    m = ChatMessageModel()
    start = time.time()
    for i in range(1000):
        m.append_user(f"message {i}")
    elapsed = time.time() - start
    assert m.rowCount() == 1000
    assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s"


def test_clear(qapp):
    m = ChatMessageModel()
    for i in range(5):
        m.append_user(f"msg {i}")
    m.clear()
    assert m.rowCount() == 0


def test_role_names(qapp):
    m = ChatMessageModel()
    names = m.roleNames()
    values = list(names.values())
    assert b"content" in values
    assert b"role" in values
    assert b"status" in values


def test_load_history_source_renders_as_system(qapp):
    """Messages with _source metadata should render as system bubbles, not user."""
    m = ChatMessageModel()
    m.load_history([
        {"role": "user", "content": "[System: subagent] task done", "_source": "subagent"},
        {"role": "assistant", "content": "summary"},
        {"role": "user", "content": "[System: cron] scheduled", "_source": "cron"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "normal user msg"},
    ])
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
