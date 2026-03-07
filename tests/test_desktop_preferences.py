from __future__ import annotations

import importlib
import sys

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QSettings = QtCore.QSettings
QGuiApplication = QtGui.QGuiApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _ini_settings(tmp_path):
    return QSettings(str(tmp_path / "desktop-prefs.ini"), QSettings.Format.IniFormat)


def test_desktop_preferences_loads_legacy_language_when_local_pref_missing(tmp_path, monkeypatch):
    from app.backend.preferences import DesktopPreferences

    monkeypatch.setattr(DesktopPreferences, "_system_is_dark", lambda self: False)
    settings = _ini_settings(tmp_path)

    prefs = DesktopPreferences(
        system_ui_language="en",
        legacy_ui_language="zh",
        settings=settings,
    )

    assert prefs.uiLanguage == "zh"
    assert prefs.effectiveLanguage == "zh"
    assert prefs.themeMode == "system"
    assert prefs.isDark is False
    assert settings.value("ui/language") == "zh"


def test_desktop_preferences_keeps_migrated_legacy_language_after_config_cleanup(
    tmp_path, monkeypatch
):
    from app.backend.preferences import DesktopPreferences

    monkeypatch.setattr(DesktopPreferences, "_system_is_dark", lambda self: False)
    settings = _ini_settings(tmp_path)

    prefs = DesktopPreferences(
        system_ui_language="en",
        legacy_ui_language="zh",
        settings=settings,
    )

    assert prefs.uiLanguage == "zh"

    reloaded = DesktopPreferences(
        system_ui_language="en",
        legacy_ui_language=None,
        settings=settings,
    )

    assert reloaded.uiLanguage == "zh"
    assert reloaded.effectiveLanguage == "zh"


def test_desktop_preferences_persists_language_and_theme_locally(tmp_path, monkeypatch):
    from app.backend.preferences import DesktopPreferences

    monkeypatch.setattr(DesktopPreferences, "_system_is_dark", lambda self: True)
    settings = _ini_settings(tmp_path)
    prefs = DesktopPreferences(system_ui_language="en", settings=settings)

    assert prefs.effectiveLanguage == "en"
    assert prefs.isDark is True

    assert prefs.setUiLanguage("zh") is True
    assert prefs.setThemeMode("light") is True

    assert prefs.uiLanguage == "zh"
    assert prefs.effectiveLanguage == "zh"
    assert prefs.themeMode == "light"
    assert prefs.isDark is False
    assert settings.value("ui/language") == "zh"
    assert settings.value("ui/themeMode") == "light"


def test_desktop_preferences_toggle_theme_switches_effective_mode(tmp_path, monkeypatch):
    from app.backend.preferences import DesktopPreferences

    monkeypatch.setattr(DesktopPreferences, "_system_is_dark", lambda self: True)
    prefs = DesktopPreferences(system_ui_language="en", settings=_ini_settings(tmp_path))

    assert prefs.themeMode == "system"
    assert prefs.isDark is True

    prefs.toggleTheme()

    assert prefs.themeMode == "light"
    assert prefs.isDark is False
