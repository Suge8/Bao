# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_sidebar_loading_state_hides_empty_cta(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        session_service = engine._test_refs["session_service"]
        empty_state = _find_object(root, "sidebarEmptyState")
        loading_state = _find_object(root, "sidebarLoadingState")

        session_service.setSessionsLoading(True)
        _process(0)

        assert bool(loading_state.property("visible")) is True
        assert bool(empty_state.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_new_session_button_click_creates_new_session(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        session_service = engine._test_refs["session_service"]
        button = _find_object(root, "newSessionButton")

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(button))
        _process(0)

        assert session_service.new_session_calls == [""]
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_empty_session_prefers_ready_state_over_hub_idle_message(qapp):
    _ = qapp
    chat_service = DummyChatService(
        EmptyMessagesModel(),
        state="idle",
        active_session_ready=True,
        active_session_has_messages=False,
    )
    engine, root = _load_main_window(chat_service=chat_service)

    try:
        ready_state = _find_object(root, "chatEmptyReadyState")
        idle_state = _find_object(root, "chatEmptyIdleState")

        _process(20)

        assert bool(ready_state.property("visible")) is True
        assert bool(idle_state.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_setup_empty_icon_uses_light_asset(qapp):
    _ = qapp
    config_service = DummyConfigService(is_valid=False, needs_setup=True)
    engine, root = _load_light_main_window(config_service=config_service)

    try:
        icon = _find_object(root, "chatEmptySetupIcon")

        assert "settings-light.svg" in str(icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_ready_empty_icon_uses_light_asset(qapp):
    _ = qapp
    chat_service = DummyChatService(
        EmptyMessagesModel(),
        state="running",
        active_session_ready=True,
        active_session_has_messages=False,
    )
    engine, root = _load_light_main_window(chat_service=chat_service)

    try:
        icon = _find_object(root, "chatEmptyReadyIcon")

        assert "chat-light.svg" in str(icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_idle_empty_icons_use_light_assets(qapp):
    _ = qapp
    engine, root = _load_light_main_window()

    try:
        idle_icon = _find_object(root, "chatEmptyIdleIcon")
        sidebar_empty_icon = _find_object(root, "sidebarEmptyChatIcon")
        sidebar_title_icon = _find_object(root, "sidebarSessionsTitleIcon")

        assert "zap-light.svg" in str(idle_icon.property("source"))
        assert "chat-light.svg" in str(sidebar_empty_icon.property("source"))
        assert "sidebar-sessions-title-light.svg" in str(sidebar_title_icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_main_greeting_tokens_use_light_values(qapp):
    _ = qapp
    engine, root = _load_light_main_window()

    try:
        assert "ignite-light.svg" in str(root.property("chatGreetingIconSource"))
        assert root.property("chatGreetingBubbleBgStart") == root.property(
            "chatGreetingBubbleBgEnd"
        )
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_session_selection_keeps_stack_bound_to_start_view(qapp):
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
        stack = _find_object(root, "mainStack")
        session_service = engine._test_refs["session_service"]

        _ = root.setProperty("startView", "settings")
        _process(20)
        assert int(stack.property("currentIndex")) == 1

        sidebar.sessionSelected.emit("desktop:local::default")
        _process(20)

        assert session_service.select_session_calls == ["desktop:local::default"]
        assert root.property("startView") == "chat"
        assert int(stack.property("currentIndex")) == 0

        _ = root.setProperty("startView", "settings")
        _process(20)

        assert int(stack.property("currentIndex")) == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_page_moves_sidebar_selection_to_app_icon(qapp):
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
        highlight = _find_object(root, "sidebarNavHighlight")
        app_icon = _find_object(root, "sidebarAppIconButton")

        _process(60)
        assert str(sidebar.property("selectionTarget")) == "sessions"
        assert bool(app_icon.property("active")) is False
        assert float(highlight.property("opacity")) > 0.0

        _ = root.setProperty("startView", "settings")
        _process(380)

        assert str(sidebar.property("selectionTarget")) == "settings"
        assert bool(app_icon.property("active")) is True
        assert float(highlight.property("opacity")) == 0.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.desktop_ui_smoke
def test_sidebar_brand_dock_keeps_logo_clear_of_diagnostics(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        app_icon = _find_object(root, "sidebarAppIconButton")
        diagnostics_pill = _find_object(root, "sidebarDiagnosticsPill")

        icon_right = float(app_icon.property("x")) + float(app_icon.property("width"))
        diagnostics_left = float(diagnostics_pill.property("x"))

        assert icon_right <= diagnostics_left - 8
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.desktop_ui_smoke
def test_sidebar_brand_dock_keeps_logo_clear_of_diagnostics_at_minimum_window_width(qapp):
    _ = qapp
    engine, root = _load_main_window(
        desktop_preferences=DummyDesktopPreferences(ui_language="en", theme_mode="light", is_dark=False)
    )

    try:
        _ = root.setProperty("width", root.property("minimumWidth"))
        _process(80)

        app_icon = _find_object(root, "sidebarAppIconButton")
        diagnostics_pill = _find_object(root, "sidebarDiagnosticsPill")

        icon_right = float(app_icon.property("x")) + float(app_icon.property("width"))
        diagnostics_left = float(diagnostics_pill.property("x"))

        assert icon_right <= diagnostics_left - 8
        _assert_item_within_window(root, diagnostics_pill, inset=8.0)
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_brand_dock_idle_logo_motion_animates_without_hover(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        motion = _find_object(root, "sidebarBrandMarkMotion")
        app_icon = _find_object(root, "sidebarAppIconButton")
        _process(120)
        first_y = float(motion.property("y"))
        first_scale = float(motion.property("scale"))

        _process(900)
        second_y = float(motion.property("y"))
        second_scale = float(motion.property("scale"))

        assert second_y != first_y
        assert second_scale != first_scale
        _assert_item_within_window(root, app_icon, inset=0.0)
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
