# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_hub_detail_bubble_width_adapts_for_short_summary(qapp):
    _ = qapp

    class HubSummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._hub_detail_value = "短摘要"

        @Property(str, constant=True)
        def hubDetail(self) -> str:
            return self._hub_detail_value

        @Property(bool, constant=True)
        def hubDetailIsError(self) -> bool:
            return False

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = HubSummaryChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        bubble = _find_object(root, "hubDetailBubble")
        orb = _find_object(root, "hubDetailOrb")

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(orb))
        _process(40)

        assert bool(bubble.property("visible")) is True
        assert float(bubble.property("width")) < 248.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("ok", "error", "expected_success", "expected_fragment"),
    [
        (True, "", True, "Session deleted"),
        (False, "boom", False, "boom"),
    ],
)
def test_delete_toast_waits_for_delete_completed(
    qapp,
    ok: bool,
    error: str,
    expected_success: bool,
    expected_fragment: str,
):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        sidebar = _find_object(root, "appSidebar")
        session_service = engine._test_refs["session_service"]
        toast = _find_toast(root)

        sidebar.sessionDeleteRequested.emit("desktop:local::default")
        _process(20)

        assert session_service.delete_session_calls == ["desktop:local::default"]
        assert toast.property("message") == ""

        session_service.deleteCompleted.emit("desktop:local::default", ok, error)
        _process(20)

        assert toast.property("message") != ""
        assert bool(toast.property("success")) is expected_success
        assert expected_fragment in str(toast.property("message"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_header_unread_badge_aggregates_unread_sessions(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": True,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
            {
                "key": "system",
                "title": "System",
                "updated_at": "2026-03-06T10:02:00",
                "channel": "system",
                "has_unread": False,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")
        badge_text = _find_object(root, "sessionsHeaderUnreadText")

        session_service.sessionsChanged.emit()

        for _ in range(4):
            _process(30)

        assert bool(badge.property("visible")) is True
        assert str(badge_text.property("text")) == "2"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_header_unread_badge_drops_active_session_immediately(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")
        badge_text = _find_object(root, "sessionsHeaderUnreadText")

        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        assert bool(badge.property("visible")) is True
        assert str(badge_text.property("text")) == "1"

        session_service.setActiveKey("telegram:room1")
        for _ in range(2):
            _process(30)

        assert bool(badge.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_unread_does_not_revive_after_switching_away(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")

        session_service.sessionsChanged.emit()
        _process(40)
        session_service.setActiveKey("telegram:room1")
        _process(40)
        session_service.setActiveKey("desktop:local::default")
        _process(40)

        assert bool(badge.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_delete_above_viewport_preserves_visible_anchor(qapp):
    _ = qapp
    rows = []
    for i in range(20):
        rows.append(
            {
                "key": f"desktop:local::s{i}",
                "title": f"Session {i}",
                "updated_at": f"2026-03-06T10:{i:02d}:00",
                "channel": "desktop",
                "has_unread": False,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_list = _find_object(root, "sidebarSessionList")

        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        session_list.setProperty("contentY", 220)
        _process(30)
        before_key, before_offset = _first_visible_sidebar_session_anchor(root, session_list)
        session_model.replaceRows(rows[1:])
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        after_offset = _sidebar_session_anchor_offset(session_list, before_key)
        after_y = float(session_list.property("contentY"))
        origin_y = float(session_list.property("originY"))
        assert isinstance(before_offset, float)
        assert isinstance(after_offset, float)
        assert after_y >= origin_y
        assert abs(after_offset - before_offset) < 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
