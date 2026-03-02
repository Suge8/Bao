"""ConfigService — reads/validates/saves ~/.bao/config.jsonc for the desktop app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, ClassVar, TypeVar, cast

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.backend.jsonc_patch import patch_jsonc, strip_comments
from bao.config.schema import Config as RuntimeConfig

_T = TypeVar("_T")
_F = TypeVar("_F", bound=Callable[..., object])


def _typed_slot(
    *types: type[object] | str,
    name: str | None = None,
    result: type[object] | str | None = None,
) -> Callable[[_F], _F]:
    if name is None and result is None:
        slot_decorator = Slot(*types)
    elif result is None:
        slot_decorator = Slot(*types, name=name)
    elif name is None:
        slot_decorator = Slot(*types, result=result)
    else:
        slot_decorator = Slot(*types, name=name, result=result)
    return cast(Callable[[_F], _F], slot_decorator)


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


class ConfigService(QObject):
    configLoaded: ClassVar[Signal] = Signal()
    saveError: ClassVar[Signal] = Signal(str)
    saveDone: ClassVar[Signal] = Signal()
    stateChanged: ClassVar[Signal] = Signal()  # notify for isValid / needsSetup

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._raw_text: str = ""
        self._data: dict[str, object] = {}
        self._config_path: Path | None = None
        self._valid: bool = False

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
        if not isinstance(model, str) or not model:
            return True
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None:
            return True
        for provider in providers.values():
            provider_dict = _as_dict(provider)
            if provider_dict and _as_str(provider_dict.get("apiKey", "")):
                return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @_typed_slot()
    def load(self) -> None:
        from bao.config.loader import get_config_path

        self._config_path = get_config_path()
        if not self._config_path.exists():
            self._valid = False
            return
        try:
            self._raw_text = self._config_path.read_text(encoding="utf-8")
            stripped = strip_comments(self._raw_text)
            raw_data = cast(object, json.loads(stripped))
            parsed_data = _as_dict(raw_data)
            if parsed_data is None:
                raise ValueError("Top-level config must be an object")
            self._data = parsed_data
            _ = RuntimeConfig.model_validate(self._data)
            dotted = self._data.get("ui.language")
            if isinstance(dotted, str):
                ui_node = _as_dict(self._data.get("ui"))
                if ui_node is None:
                    ui_node = {}
                    self._data["ui"] = ui_node
                _ = ui_node.setdefault("language", dotted)
            self._valid = True
            self._notify_state_changed()
            self.configLoaded.emit()
        except Exception as e:
            self._valid = False
            self.saveError.emit(f"Failed to load config: {e}")

    def get(self, dotpath: str, default: _T | None = None) -> object | _T | None:
        """Read a value by dot-separated path."""
        parts = dotpath.split(".")
        node: object = self._data
        for part in parts:
            current = _as_dict(node)
            if current is None or part not in current:
                return default
            node = current[part]
        return node

    @_typed_slot(str, result="QVariant")
    def getValue(self, dotpath: str) -> object | None:
        return self.get(dotpath)

    @_typed_slot(result="QVariant")
    def getFirstProvider(self) -> dict[str, object]:
        """Return {name, type, apiKey, apiBase} of the first provider, or empty dict."""
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None or not providers:
            return {}
        name = next(iter(providers))
        provider = _as_dict(providers[name])
        if provider is None:
            return {}
        return {
            "name": name,
            "type": _as_str(provider.get("type", "")),
            "apiKey": _as_str(provider.get("apiKey", "")),
            "apiBase": _as_str(provider.get("apiBase", "")),
        }

    @_typed_slot(result="QVariant")
    def getProviders(self) -> list[dict[str, object]]:
        """Return list of {name, type, apiKey, apiBase, extraHeaders} for all providers."""
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None:
            return []
        result: list[dict[str, object]] = []
        for name, provider in providers.items():
            provider_dict = _as_dict(provider)
            if provider_dict is None:
                continue
            extra_headers = _as_dict(provider_dict.get("extraHeaders")) or {}
            result.append(
                {
                    "name": name,
                    "type": _as_str(provider_dict.get("type", "")),
                    "apiKey": _as_str(provider_dict.get("apiKey", "")),
                    "apiBase": _as_str(provider_dict.get("apiBase", "")),
                    "extraHeaders": extra_headers,
                }
            )
        return result

    @_typed_slot(str, result=bool)
    def removeProvider(self, name: str) -> bool:
        """Remove a provider by name. Rewrites the providers object."""
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None or name not in providers:
            return False
        new_providers: dict[str, object] = {
            key: value for key, value in providers.items() if key != name
        }
        return self.save({"providers": new_providers})

    @_typed_slot("QVariantMap", result=bool)
    def save(self, changes: dict[str, object]) -> bool:
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
        try:
            result, errors = patch_jsonc(text, changes)
        except Exception as e:
            self.saveError.emit(f"Patch failed: {e}")
            return False
        if errors:
            msgs = "; ".join(e.message for e in errors)
            self.saveError.emit(f"Patch errors: {msgs}")
            return False

        try:
            stripped = strip_comments(result)
            raw_candidate = cast(object, json.loads(stripped))
            candidate = _as_dict(raw_candidate)
            if candidate is None:
                raise ValueError("Top-level config must be an object")
            _ = RuntimeConfig.model_validate(candidate)
        except Exception as e:
            self.saveError.emit(f"Config validation failed: {e}")
            return False

        try:
            _ = self._config_path.write_text(result, encoding="utf-8")
            self._raw_text = result
            self._data = candidate
            self._valid = True
            self._notify_state_changed()
            self.saveDone.emit()
            return True
        except Exception as e:
            self.saveError.emit(f"Write failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, changes: dict[str, object]) -> str | None:
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
                token_value = changes.get(token_path)
                if not isinstance(token_value, str):
                    saved_token = self.get(token_path, "")
                    token = saved_token if isinstance(saved_token, str) else ""
                else:
                    token = token_value
                if not token:
                    channel = enabled_path.split(".")[1]
                    return f"token_required:{channel}"
        return None

    def _notify_state_changed(self) -> None:
        """Emit stateChanged so QML re-evaluates isValid / needsSetup."""
        self.stateChanged.emit()

    def _collapse_missing_intermediates(self, changes: dict[str, object]) -> dict[str, object]:
        """Collapse dotpaths whose intermediate keys don't exist in self._data.

        Example::

            {"providers.x.type": "openai", "providers.x.apiKey": "sk-"}
            -> {"providers.x": {"type": "openai", "apiKey": "sk-"}}

        This lets patch_jsonc insert a single key into an existing parent
        object instead of failing on missing intermediate keys.
        """
        passthrough: dict[str, object] = {}
        needs_collapse: dict[str, dict[str, object]] = {}

        for dotpath, value in changes.items():
            parts = dotpath.split(".")
            if len(parts) < 3:
                # 2-level or less — patch_jsonc can handle directly
                passthrough[dotpath] = value
                continue

            # Check deepest existing ancestor in self._data
            node: object = self._data
            depth = 0
            for p in parts[:-1]:
                node_dict = _as_dict(node)
                if node_dict is not None and p in node_dict:
                    node = node_dict[p]
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
                _ = needs_collapse.setdefault(collapse_key, {})
                needs_collapse[collapse_key][leaf_key] = value

        # Build collapsed entries as nested dicts
        for collapse_key, flat_leaves in needs_collapse.items():
            obj: dict[str, object] = {}
            for leaf_path, val in flat_leaves.items():
                leaf_parts = leaf_path.split(".")
                target = obj
                for k in leaf_parts[:-1]:
                    nested = _as_dict(target.get(k))
                    if nested is None:
                        nested = {}
                        target[k] = nested
                    target = nested
                target[leaf_parts[-1]] = val
            passthrough[collapse_key] = obj

        return passthrough
