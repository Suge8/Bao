# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_testkit import *

def test_diagnostics_modal_renders_content(qapp):
    _ = qapp
    engine, root = _load_main_window(
        chat_service=DummyChatService(EmptyMessagesModel(), state="running"),
        diagnostics_service=DummyDiagnosticsService(),
    )

    try:
        modal = _find_object(root, "diagnosticsModal")
        _ = QMetaObject.invokeMethod(modal, "open")
        _process(150)

        _find_object_by_property(root, "text", "Hub State")
        _find_object_by_property(root, "text", "Running normally")
        _find_object_by_property(root, "text", "Log file")
        _find_object_by_property(root, "text", "/tmp/bao-desktop.log")
        _find_object_by_property(root, "text", "Log tail")

        hub_card = _find_object(root, "diagnosticsHubCard")
        log_file_card = _find_object(root, "diagnosticsLogFileCard")
        events_card = _find_object(root, "diagnosticsEventsCard")
        log_tail_card = _find_object(root, "diagnosticsLogTailCard")

        assert int(hub_card.property("width")) > 260
        assert int(log_file_card.property("width")) > 260
        assert int(events_card.property("width")) > 260
        assert int(log_tail_card.property("width")) > 260
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_diagnostics_log_tail_follow_contract_preserves_manual_detach_and_resume(qapp):
    _ = qapp
    diagnostics_service = DummyDiagnosticsService()
    diagnostics_service._recent_log_text = "\n".join(
        f"2026-03-08 03:19:{i:02d} | INFO | line {i}" for i in range(240)
    )
    engine, root = _load_main_window(
        chat_service=DummyChatService(EmptyMessagesModel(), state="running"),
        diagnostics_service=diagnostics_service,
    )

    try:
        modal = _find_object(root, "diagnosticsModal")
        _ = QMetaObject.invokeMethod(modal, "open")
        _process(50)

        scroll = _find_object(root, "diagnosticsLogTailScroll")
        _wait_for_diagnostics_log_tail_ready(root, scroll)
        flick = scroll

        max_y = max(0.0, float(flick.property("contentHeight")) - float(flick.property("height")))
        assert max_y > 0
        assert abs(float(flick.property("contentY")) - max_y) <= 2
        assert bool(scroll.property("autoFollowActive")) is True

        detached_y = 0.0
        _ = flick.setProperty("contentY", detached_y)
        _ = QMetaObject.invokeMethod(scroll, "refreshAutoFollowFromViewport")
        _process(20)
        assert bool(scroll.property("autoFollowActive")) is False
        assert abs(float(flick.property("contentY")) - detached_y) <= 2

        diagnostics_service._recent_log_text += "\n2026-03-08 03:20:00 | INFO | line while detached"
        diagnostics_service.changed.emit()
        _process(200)

        detached_max_y = max(
            0.0, float(flick.property("contentHeight")) - float(flick.property("height"))
        )
        assert detached_max_y > detached_y
        assert float(flick.property("contentY")) < detached_max_y - 8.0
        assert bool(scroll.property("autoFollowActive")) is False

        _ = QMetaObject.invokeMethod(scroll, "followTail")
        _wait_until(lambda: not bool(scroll.property("scrollToEndQueued")))
        assert bool(scroll.property("autoFollowActive")) is True

        diagnostics_service._recent_log_text += "\n2026-03-08 03:20:01 | INFO | line after resume"
        diagnostics_service.changed.emit()
        _process(200)

        resumed_max_y = max(
            0.0, float(flick.property("contentHeight")) - float(flick.property("height"))
        )
        assert abs(float(flick.property("contentY")) - resumed_max_y) <= 2
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_diagnostics_log_tail_reopen_resets_follow_to_latest_log(qapp):
    _ = qapp
    diagnostics_service = DummyDiagnosticsService()
    diagnostics_service._recent_log_text = "\n".join(
        f"2026-03-08 03:21:{i:02d} | INFO | line {i}" for i in range(240)
    )
    engine, root = _load_main_window(
        chat_service=DummyChatService(EmptyMessagesModel(), state="running"),
        diagnostics_service=diagnostics_service,
    )

    try:
        modal = _find_object(root, "diagnosticsModal")
        _ = QMetaObject.invokeMethod(modal, "open")
        _process(50)

        scroll = _find_object(root, "diagnosticsLogTailScroll")
        _wait_for_diagnostics_log_tail_ready(root, scroll)
        initial_max_y = max(
            0.0, float(scroll.property("contentHeight")) - float(scroll.property("height"))
        )
        assert initial_max_y > 0
        assert abs(float(scroll.property("contentY")) - initial_max_y) <= 2
        assert bool(scroll.property("autoFollowActive")) is True

        _ = QMetaObject.invokeMethod(modal, "close")
        _process(120)

        diagnostics_service._recent_log_text += "\n2026-03-08 03:22:00 | INFO | line while hidden"
        diagnostics_service.changed.emit()
        _process(120)

        _ = QMetaObject.invokeMethod(modal, "open")
        _process(50)
        _wait_for_diagnostics_log_tail_ready(root, scroll)

        max_y = max(0.0, float(scroll.property("contentHeight")) - float(scroll.property("height")))
        assert max_y > 0
        assert bool(scroll.property("autoFollowActive")) is True
        assert abs(float(scroll.property("contentY")) - max_y) <= 2
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_external_click_clears_selection_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        message_input = _find_chat_input(root)

        _ = message_input.setProperty("text", "hello bao")
        message_input.forceActiveFocus()
        _process(0)
        message_input.select(0, 5)
        _process(0)

        assert bool(message_input.property("activeFocus")) is True
        assert str(message_input.property("selectedText")) == "hello"

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(20, 120))
        _process(0)

        assert bool(message_input.property("activeFocus")) is False
        assert str(message_input.property("selectedText")) == ""
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_setup_mode_hides_sidebar_and_lands_on_settings(qapp):
    _ = qapp
    engine, root = _load_main_window(DummyConfigService(is_valid=False, needs_setup=True))

    try:
        sidebar = _find_object(root, "appSidebar")
        stack = _find_object(root, "mainStack")

        assert bool(root.property("setupMode")) is True
        assert bool(sidebar.property("visible")) is False
        assert int(stack.property("currentIndex")) == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_advanced_section_shows_config_folder_entry(qapp):
    _ = qapp
    config_service = DummyConfigService(config_file_path="/tmp/.bao/config.jsonc")
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 2)
        _process(30)

        open_button = _find_visible_object_by_property(root, "text", "Open Config Folder")
        _find_object_by_property(root, "text", "/tmp/.bao/config.jsonc")

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(open_button))
        _process(0)

        assert config_service.opened_config_directory is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_onboarding_invalid_ui_language_stays_on_first_step(qapp):
    _ = qapp
    config_service = DummyConfigService(is_valid=False, needs_setup=True, language="fr")
    engine, root = _load_main_window(
        config_service,
        desktop_preferences=DummyDesktopPreferences(ui_language="fr"),
    )

    try:
        settings_view = _find_object(root, "settingsView")

        assert bool(root.property("setupMode")) is True
        assert settings_view.property("onboardingUiLanguage") == "auto"
        assert bool(settings_view.property("languageConfigured")) is False
        assert int(settings_view.property("onboardingStepIndex")) == 0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_onboarding_custom_model_preset_clears_previous_recommended_value(qapp):
    _ = qapp
    config_service = DummyConfigService(
        is_valid=False,
        needs_setup=True,
        model="openai/gpt-4o",
    )
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = settings_view.setProperty(
            "_providerList",
            [{"name": "primary", "type": "openai", "apiKey": "sk-ok", "apiBase": ""}],
        )
        _process(30)

        assert settings_view.property("onboardingDraftModel") == "openai/gpt-4o"
        assert QMetaObject.invokeMethod(settings_view, "activateCustomModelInput")
        assert settings_view.property("onboardingDraftModel") == ""
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
