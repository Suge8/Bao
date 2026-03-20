# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_sidebar_brand_dock_uses_circular_logo_asset(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        brand_icon = _find_object(root, "sidebarBrandMarkIcon")
        source = str(brand_icon.property("source"))
        assert "logo-circle.png" in source, source
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_brand_dock_keeps_diagnostics_content_centered(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        pill = _find_object(root, "sidebarDiagnosticsPill")
        icon_chip = _find_object(root, "sidebarDiagnosticsIconChip")
        label_stack = _find_object(root, "sidebarDiagnosticsLabelStack")

        pill_center_y = pill.mapToScene(QPointF(0.0, float(pill.property("height")) / 2.0)).y()
        icon_center_y = icon_chip.mapToScene(
            QPointF(0.0, float(icon_chip.property("height")) / 2.0)
        ).y()
        label_center_y = label_stack.mapToScene(
            QPointF(0.0, float(label_stack.property("height")) / 2.0)
        ).y()

        assert abs(icon_center_y - pill_center_y) <= 1.0
        assert abs(label_center_y - pill_center_y) <= 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_brand_dock_uses_compact_diagnostics_metrics(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        pill = _find_object(root, "sidebarDiagnosticsPill")
        content_row = _find_object(root, "sidebarDiagnosticsContentRow")

        assert int(pill.property("width")) == 104
        assert int(content_row.property("spacing")) == 14
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_detail_bubble_shows_error_without_hover(qapp):
    _ = qapp

    class HubDetailChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._state_value = "running"
            self._last_error_value = "⚠ Channel start failed: telegram: bad token"
            self._hub_detail_value = self._last_error_value

        @Property(str, constant=True)
        def state(self) -> str:
            return self._state_value

        @Property(str, constant=True)
        def lastError(self) -> str:
            return self._last_error_value

        @Property(str, constant=True)
        def hubDetail(self) -> str:
            return self._hub_detail_value

        @Property(bool, constant=True)
        def hubDetailIsError(self) -> bool:
            return True

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
    chat_service = HubDetailChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "hubDetailOrb")
        bubble = _find_object(root, "hubDetailBubble")
        text = _find_object(root, "hubDetailText")

        assert bool(orb.property("visible")) is True
        assert bool(bubble.property("visible")) is False

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(orb))
        _process(40)

        assert bool(bubble.property("visible")) is True
        assert "telegram" in str(text.property("text"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_detail_bubble_shows_summary_on_hover(qapp):
    _ = qapp

    class HubSummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._hub_detail_value = "✓ Hub started — channels: telegram"

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
        text = _find_object(root, "hubDetailText")

        assert bool(bubble.property("visible")) is False

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        orb = _find_object(root, "hubDetailOrb")
        QTest.mouseMove(root, _center_point(orb))
        _process(40)
        if not bool(bubble.property("visible")):
            QTest.mouseMove(root, _center_point(orb))
            _process(40)

        assert bool(bubble.property("visible")) is True
        assert "Hub started" in str(text.property("text"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_detail_bubble_stays_hidden_on_focus_without_hover(qapp):
    _ = qapp

    class HubSummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._hub_detail_value = "✓ Hub started — channels: telegram"

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
        orb = _find_object(root, "hubDetailOrb")
        bubble = _find_object(root, "hubDetailBubble")
        capsule = _find_object(root, "hubCapsule")

        assert bool(bubble.property("visible")) is False
        assert bool(orb.property("visible")) is True
        capsule.forceActiveFocus()
        _process(20)

        assert bool(capsule.property("activeFocus")) is True
        assert bool(bubble.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_hub_capsule_is_keyboard_focusable(qapp):
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
    chat_service = DummyChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        capsule = _find_object(root, "hubCapsule")
        assert bool(capsule.property("activeFocusOnTab")) is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
