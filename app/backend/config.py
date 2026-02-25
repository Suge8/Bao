"""ConfigService — reads/validates/saves ~/.bao/config.jsonc for the desktop app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot, Property

from app.backend.jsonc_patch import patch_jsonc, _strip_comments
from bao.config.schema import Config as RuntimeConfig


class ConfigService(QObject):
    configLoaded = Signal()
    saveError = Signal(str)
    saveDone = Signal()
    stateChanged = Signal()  # notify for isValid / needsSetup

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._raw_text: str = ""
        self._data: dict = {}
        self._config_path: Path | None = None
        self._valid = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(bool, notify=stateChanged)
    def isValid(self) -> bool:
        return self._valid

    @Property(bool, notify=stateChanged)
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
            RuntimeConfig.model_validate(self._data)
            dotted = self._data.get("ui.language")
            if isinstance(dotted, str):
                ui_node = self._data.get("ui")
                if not isinstance(ui_node, dict):
                    ui_node = {}
                    self._data["ui"] = ui_node
                ui_node.setdefault("language", dotted)
            self._valid = True
            self._notify_state_changed()
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
        """Return {name, type, apiKey, apiBase} of the first provider, or empty dict."""
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
        }

    @Slot(result="QVariant")
    def getProviders(self) -> list:
        """Return list of {name, type, apiKey, apiBase, extraHeaders} for all providers."""
        providers = self._data.get("providers", {})
        if not isinstance(providers, dict):
            return []
        result = []
        for name, p in providers.items():
            if not isinstance(p, dict):
                continue
            result.append(
                {
                    "name": name,
                    "type": p.get("type", ""),
                    "apiKey": p.get("apiKey", ""),
                    "apiBase": p.get("apiBase", ""),
                    "extraHeaders": p.get("extraHeaders") or {},
                }
            )
        return result

    @Slot(str, result=bool)
    def removeProvider(self, name: str) -> bool:
        """Remove a provider by name. Rewrites the providers object."""
        providers = self._data.get("providers", {})
        if not isinstance(providers, dict) or name not in providers:
            return False
        new_providers = {k: v for k, v in providers.items() if k != name}
        return self.save({"providers": new_providers})

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

        # Collapse nested dotpaths whose intermediate keys don't exist yet.
        # e.g. {"providers.x.type": "openai", "providers.x.apiKey": "sk-"}
        #   -> {"providers.x": {"type": "openai", "apiKey": "sk-"}}
        changes = self._collapse_missing_intermediates(changes)

        text = self._raw_text or "{}"
        result, errors = patch_jsonc(text, changes)
        if errors:
            msgs = "; ".join(e.message for e in errors)
            self.saveError.emit(f"Patch errors: {msgs}")
            return False

        try:
            stripped = _strip_comments(result)
            candidate = json.loads(stripped)
            RuntimeConfig.model_validate(candidate)
        except Exception as e:
            self.saveError.emit(f"Config validation failed: {e}")
            return False

        try:
            self._config_path.write_text(result, encoding="utf-8")
            self._raw_text = result
            self._data = candidate
            self._notify_state_changed()
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
            # WhatsApp bridgeToken is optional — no validation needed
        }
        for enabled_path, token_path in channel_token_fields.items():
            if changes.get(enabled_path) is True:
                token = changes.get(token_path) or self.get(token_path, "")
                if not token:
                    channel = enabled_path.split(".")[1]
                    return f"token_required:{channel}"
        return None

    def _notify_state_changed(self) -> None:
        """Emit stateChanged so QML re-evaluates isValid / needsSetup."""
        self.stateChanged.emit()

    def _collapse_missing_intermediates(self, changes: dict) -> dict:
        """Collapse dotpaths whose intermediate keys don't exist in self._data.

        Example::

            {"providers.x.type": "openai", "providers.x.apiKey": "sk-"}
            -> {"providers.x": {"type": "openai", "apiKey": "sk-"}}

        This lets patch_jsonc insert a single key into an existing parent
        object instead of failing on missing intermediate keys.
        """
        passthrough: dict[str, Any] = {}
        needs_collapse: dict[str, dict[str, Any]] = {}

        for dotpath, value in changes.items():
            parts = dotpath.split(".")
            if len(parts) < 3:
                # 2-level or less — patch_jsonc can handle directly
                passthrough[dotpath] = value
                continue

            # Check deepest existing ancestor in self._data
            node = self._data
            depth = 0
            for p in parts[:-1]:
                if isinstance(node, dict) and p in node:
                    node = node[p]
                    depth += 1
                else:
                    break

            if depth == len(parts) - 1:
                # Full intermediate path exists — keep original dotpath
                passthrough[dotpath] = value
            else:
                # Collapse: group under the deepest existing ancestor + 1
                collapse_key = ".".join(parts[: depth + 1])
                leaf_key = ".".join(parts[depth + 1 :])
                needs_collapse.setdefault(collapse_key, {})
                needs_collapse[collapse_key][leaf_key] = value

        # Build collapsed entries as nested dicts
        for collapse_key, flat_leaves in needs_collapse.items():
            obj: dict[str, Any] = {}
            for leaf_path, val in flat_leaves.items():
                leaf_parts = leaf_path.split(".")
                target = obj
                for k in leaf_parts[:-1]:
                    target = target.setdefault(k, {})
                target[leaf_parts[-1]] = val
            passthrough[collapse_key] = obj

        return passthrough
