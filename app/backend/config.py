"""ConfigService — reads/validates/saves ~/.bao/config.jsonc for the desktop app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot, Property

from app.backend.jsonc_patch import patch_jsonc, _strip_comments


class ConfigService(QObject):
    configLoaded = Signal()
    saveError = Signal(str)
    saveDone = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._raw_text: str = ""
        self._data: dict = {}
        self._config_path: Path | None = None
        self._valid = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(bool, constant=False)
    def isValid(self) -> bool:
        return self._valid

    @Property(bool, constant=False)
    def needsSetup(self) -> bool:
        """True if config exists but is not fully configured (no model or no apiKey)."""
        if not self._valid:
            return True
        model = self.get("agents.defaults.model", "")
        if not model:
            return True
        providers = self._data.get("providers", {})
        if not isinstance(providers, dict):
            return True
        for p in providers.values():
            if isinstance(p, dict) and p.get("apiKey", ""):
                return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @Slot()
    def load(self) -> None:
        from bao.config.loader import get_config_path

        self._config_path = get_config_path()
        if not self._config_path.exists():
            self._valid = False
            return
        try:
            self._raw_text = self._config_path.read_text(encoding="utf-8")
            stripped = _strip_comments(self._raw_text)
            self._data = json.loads(stripped)
            dotted = self._data.get("ui.language")
            if isinstance(dotted, str):
                ui_node = self._data.get("ui")
                if not isinstance(ui_node, dict):
                    ui_node = {}
                    self._data["ui"] = ui_node
                ui_node.setdefault("language", dotted)
            self._valid = True
            self.configLoaded.emit()
        except Exception as e:
            self._valid = False
            self.saveError.emit(f"Failed to load config: {e}")

    def get(self, dotpath: str, default: Any = None) -> Any:
        """Read a value by dot-separated path."""
        parts = dotpath.split(".")
        node = self._data
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    @Slot(str, result="QVariant")
    def getValue(self, dotpath: str) -> Any:
        return self.get(dotpath)

    @Slot(result="QVariant")
    def getFirstProvider(self) -> dict:
        """Return {name, type, apiKey, apiBase, apiMode} of the first provider, or empty dict."""
        providers = self._data.get("providers", {})
        if not isinstance(providers, dict) or not providers:
            return {}
        name = next(iter(providers))
        p = providers[name]
        if not isinstance(p, dict):
            return {}
        return {
            "name": name,
            "type": p.get("type", ""),
            "apiKey": p.get("apiKey", ""),
            "apiBase": p.get("apiBase", ""),
            "apiMode": p.get("apiMode", ""),
        }

    @Slot("QVariantMap", result=bool)
    def save(self, changes: dict) -> bool:
        """Apply *changes* (dotpath -> value) and write back preserving comments."""
        if self._config_path is None:
            self.saveError.emit("Config path not set — call load() first")
            return False

        # Validate required fields
        err = self._validate(changes)
        if err:
            self.saveError.emit(err)
            return False

        text = self._raw_text or "{}"
        result, errors = patch_jsonc(text, changes)
        if errors:
            msgs = "; ".join(e.message for e in errors)
            self.saveError.emit(f"Patch errors: {msgs}")
            return False

        try:
            self._config_path.write_text(result, encoding="utf-8")
            self._raw_text = result
            stripped = _strip_comments(result)
            self._data = json.loads(stripped)
            self.saveDone.emit()
            return True
        except Exception as e:
            self.saveError.emit(f"Write failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, changes: dict) -> str | None:
        """Return error string if validation fails, else None."""
        # Check: if a channel is being enabled, its token must be present
        channel_token_fields = {
            "channels.telegram.enabled": "channels.telegram.token",
            "channels.discord.enabled": "channels.discord.token",
            "channels.slack.enabled": "channels.slack.botToken",
            "channels.whatsapp.enabled": "channels.whatsapp.bridgeToken",
        }
        for enabled_path, token_path in channel_token_fields.items():
            if changes.get(enabled_path) is True:
                token = changes.get(token_path) or self.get(token_path, "")
                if not token:
                    channel = enabled_path.split(".")[1]
                    return f"{channel}: token is required when enabled"
        return None
