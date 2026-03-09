"""Tests for ChatMessageModel."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from unittest.mock import patch

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.unit, pytest.mark.gui]

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


@pytest.mark.smoke
def test_append_user(qapp):
    m = _new_model()
    row = m.append_user("hello")
    assert row == 0
    assert m.rowCount() == 1
    idx = m.index(0)
    assert m.data(idx, Qt.UserRole + 2) == "user"
    assert m.data(idx, Qt.UserRole + 3) == "hello"
    assert m.data(idx, Qt.UserRole + 7) == "userSent"
    assert m.data(idx, Qt.UserRole + 8) is True


@pytest.mark.smoke
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
            {"role": "user", "content": "gateway started", "_source": "desktop-system"},
            {"role": "assistant", "content": "summary"},
            {"role": "user", "content": "[System: cron] scheduled", "_source": "cron"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "normal user msg"},
        ]
    )
    assert m.rowCount() == 5
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
    _ = m.append_assistant("hello", status="done", entrance_pending=True)
    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "hello", "status": "done"}]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)

    assert len(resets) == 0


def test_load_prepared_updates_same_length_assistant_row_without_reset(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    _ = m.append_assistant("", status="typing", entrance_pending=True)
    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "hello", "status": "done", "format": "markdown"}]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)

    assert resets == []
    assert m._messages[0]["content"] == "hello"
    assert m._messages[0]["status"] == "done"


def test_load_prepared_preserves_transient_assistant_tail_when_requested(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    _ = m.append_user("hello")
    _ = m.append_assistant("working", status="done")
    _ = m.append_assistant("", status="typing")
    prepared = ChatMessageModel.prepare_history(
        [{"role": "user", "content": "hello"}, {"role": "tool", "content": "running tool"}]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared, preserve_transient_tail=True)

    assert resets == []
    assert m.rowCount() == 4
    assert m._messages[1]["role"] == "system"
    assert m._messages[2]["content"] == "working"
    assert m._messages[3]["status"] == "typing"


def test_load_prepared_reconciles_tool_row_and_final_assistant_without_reset(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    _ = m.append_user("hello")
    _ = m.append_assistant("working", status="done")
    _ = m.append_assistant("", status="typing")
    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "running tool"},
            {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
        ]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared, preserve_transient_tail=True)

    assert resets == []
    assert m.rowCount() == 3
    assert m._messages[1]["role"] == "system"
    assert m._messages[2]["content"] == "final"
    assert m._messages[2]["status"] == "done"


def test_load_prepared_reconciles_completed_assistant_tail_without_reset(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    _ = m.append_user("hello")
    _ = m.append_assistant("working", status="done")
    _ = m.append_assistant("final", status="done")
    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "running tool"},
            {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
        ]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)

    assert resets == []
    assert m.rowCount() == 3
    assert m._messages[1]["role"] == "system"
    assert m._messages[2]["content"] == "final"
    assert m._messages[2]["status"] == "done"


def test_load_prepared_reconciles_assistant_only_split_without_reset(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    _ = m.append_user("hello")
    _ = m.append_assistant("first", status="typing")
    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "first", "status": "done", "format": "markdown"},
            {"role": "assistant", "content": "second", "status": "done", "format": "markdown"},
        ]
    )
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)

    assert resets == []
    assert m.rowCount() == 3
    assert m._messages[1]["content"] == "first"
    assert m._messages[1]["status"] == "done"
    assert m._messages[2]["content"] == "second"
    assert m._messages[2]["status"] == "done"


def test_load_prepared_resets_when_system_entrance_style_changes(qapp):
    from app.backend.chat import ChatMessageModel

    m = _new_model()
    prepared = ChatMessageModel.prepare_history(
        [{"role": "system", "content": "hello", "entrance_style": "system"}]
    )
    changed = [dict(prepared[0], entrancestyle="greeting")]
    resets = []
    m.modelReset.connect(lambda: resets.append(True))

    m.load_prepared(prepared)
    m.load_prepared(changed)

    assert len(resets) == 2


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


def test_prepare_history_preserves_system_entrance_style(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "system", "content": "hello", "entrance_style": "greeting"},
            {
                "role": "user",
                "content": "notice",
                "_source": "desktop-system",
                "entrance_style": "system",
            },
            {"role": "tool", "content": "work", "entrance_style": "system"},
        ]
    )

    assert prepared[0]["entrancestyle"] == "greeting"
    assert prepared[1]["entrancestyle"] == "system"
    assert prepared[2]["entrancestyle"] == "system"


def test_prepare_history_invalid_entrance_style_falls_back_none(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "system", "content": "hello", "entrance_style": "bad-style"},
            {"role": "user", "content": "notice", "_source": "desktop-system", "entrance_style": 1},
            {"role": "tool", "content": "work", "entrance_style": None},
        ]
    )

    assert prepared[0]["entrancestyle"] == "none"
    assert prepared[1]["entrancestyle"] == "none"
    assert prepared[2]["entrancestyle"] == "none"


def test_normalize_entrance_style_accepts_user_sent(qapp):
    from app.backend.chat import ChatMessageModel

    assert ChatMessageModel._normalize_entrance_style("userSent") == "userSent"


def test_prepare_history_invalid_status_falls_back_done(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "assistant", "content": "a", "status": "bad"},
            {"role": "system", "content": "s", "status": 1},
            {"role": "user", "content": "u", "_source": "desktop-system", "status": None},
        ]
    )

    assert prepared[0]["status"] == "done"
    assert prepared[1]["status"] == "done"
    assert prepared[2]["status"] == "done"


def test_prepare_history_preserves_assistant_markdown_format(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "[bao](https://bao.bot)", "format": "markdown"}]
    )

    assert prepared[0]["format"] == "markdown"


def test_prepare_history_defaults_assistant_format_to_markdown(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history([{"role": "assistant", "content": "**bao**"}])

    assert prepared[0]["format"] == "markdown"


def test_prepare_history_preserves_created_at_from_iso_string(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [{"role": "assistant", "content": "hi", "created_at": "2024-01-02T03:04:05+00:00"}]
    )

    assert prepared[0]["createdat"] == 1704164645000


def test_prepare_history_preserves_created_at_from_epoch_millis(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [{"role": "user", "content": "hi", "created_at": 1704164645000}]
    )

    assert prepared[0]["createdat"] == 1704164645000


def test_prepare_history_adds_gap_divider_text(qapp):
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [
            {"role": "user", "content": "morning", "created_at": "2024-01-02T09:00:00"},
            {"role": "assistant", "content": "night", "created_at": "2024-01-02T18:30:00"},
        ]
    )

    assert prepared[0]["dividertext"] == ""
    assert prepared[1]["dividertext"] == "2024/1/2"


def test_prepare_history_uses_time_for_same_day_gap_today(qapp):
    from app.backend.chat import ChatMessageModel

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 7, 20, 0, 0, tzinfo=tz)

    with patch("app.backend.chat.datetime", FrozenDateTime):
        prepared = ChatMessageModel.prepare_history(
            [
                {"role": "user", "content": "morning", "created_at": "2026-03-07T09:00:00"},
                {
                    "role": "assistant",
                    "content": "night",
                    "created_at": "2026-03-07T18:30:00",
                },
            ]
        )

    assert prepared[1]["dividertext"] == "18:30"
