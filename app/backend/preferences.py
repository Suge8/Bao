from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Property, QObject, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QPalette, QStyleHints


class DesktopPreferences(QObject):
    uiLanguageChanged: ClassVar[Signal] = Signal()
    effectiveLanguageChanged: ClassVar[Signal] = Signal()
    themeModeChanged: ClassVar[Signal] = Signal()
    isDarkChanged: ClassVar[Signal] = Signal()

    _LANGUAGE_KEY: ClassVar[str] = "ui/language"
    _THEME_KEY: ClassVar[str] = "ui/themeMode"
    _SUPPORTED_UI_LANGUAGES: ClassVar[set[str]] = {"auto", "zh", "en"}
    _SUPPORTED_THEME_MODES: ClassVar[set[str]] = {"system", "light", "dark"}

    def __init__(
        self,
        *,
        system_ui_language: str,
        legacy_ui_language: str | None = None,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings: QSettings = settings or QSettings("Bao", "Desktop")
        self._system_ui_language: str = self._sanitize_ui_language(
            system_ui_language, fallback="en"
        )
        self._ui_language: str = self._load_ui_language(legacy_ui_language)
        stored_theme_mode = self._settings.value(self._THEME_KEY, "system")
        self._theme_mode: str = self._sanitize_theme_mode(stored_theme_mode)
        self._style_hints: QStyleHints = QGuiApplication.styleHints()
        self._is_dark: bool = self._resolve_is_dark()
        _ = self._style_hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)

    @Property(str, notify=uiLanguageChanged)
    def uiLanguage(self) -> str:
        return self._ui_language

    @Property(str, notify=effectiveLanguageChanged)
    def effectiveLanguage(self) -> str:
        if self._ui_language in {"zh", "en"}:
            return self._ui_language
        return self._system_ui_language

    @Property(str, notify=themeModeChanged)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(bool, notify=isDarkChanged)
    def isDark(self) -> bool:
        return self._is_dark

    @Slot(str, result=bool)
    def setUiLanguage(self, value: str) -> bool:
        next_value = self._sanitize_ui_language(value)
        if next_value == self._ui_language:
            return True
        previous_effective = self.effectiveLanguage
        self._ui_language = next_value
        self._settings.setValue(self._LANGUAGE_KEY, next_value)
        self.uiLanguageChanged.emit()
        if self.effectiveLanguage != previous_effective:
            self.effectiveLanguageChanged.emit()
        return True

    @Slot(str, result=bool)
    def setThemeMode(self, value: str) -> bool:
        next_value = self._sanitize_theme_mode(value)
        next_is_dark = self._resolve_is_dark(next_value)
        if next_value == self._theme_mode and next_is_dark == self._is_dark:
            return True
        self._theme_mode = next_value
        self._settings.setValue(self._THEME_KEY, next_value)
        self.themeModeChanged.emit()
        self._set_is_dark(next_is_dark)
        return True

    @Slot()
    def toggleTheme(self) -> None:
        _ = self.setThemeMode("light" if self._is_dark else "dark")

    def _set_is_dark(self, next_is_dark: bool) -> None:
        previous_is_dark = self._is_dark
        self._is_dark = next_is_dark
        if next_is_dark != previous_is_dark:
            self.isDarkChanged.emit()

    def _resolve_is_dark(self, theme_mode: str | None = None) -> bool:
        mode = theme_mode or self._theme_mode
        if mode == "dark":
            return True
        if mode == "light":
            return False
        return self._system_is_dark()

    def _system_is_dark(self) -> bool:
        scheme = self._style_hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False

        try:
            palette = QGuiApplication.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            return window_color.lightness() < 128
        except Exception:
            return False

    def _sanitize_ui_language(self, value: object, fallback: str = "auto") -> str:
        return self._sanitize_choice(value, self._SUPPORTED_UI_LANGUAGES, fallback)

    def _load_ui_language(self, legacy_ui_language: str | None) -> str:
        if self._settings.contains(self._LANGUAGE_KEY):
            stored_ui_language = self._settings.value(self._LANGUAGE_KEY, "auto")
            return self._sanitize_ui_language(stored_ui_language)

        legacy_value = self._sanitize_ui_language(legacy_ui_language or "auto")
        if legacy_value != "auto":
            self._settings.setValue(self._LANGUAGE_KEY, legacy_value)
        return legacy_value

    def _sanitize_theme_mode(self, value: object) -> str:
        return self._sanitize_choice(value, self._SUPPORTED_THEME_MODES, "system")

    def _sanitize_choice(self, value: object, supported: set[str], fallback: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in supported:
                return normalized
        return fallback

    @Slot(object)
    def _on_system_color_scheme_changed(self, _scheme: object) -> None:
        if self._theme_mode != "system":
            return
        self._set_is_dark(self._resolve_is_dark("system"))
