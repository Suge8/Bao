"""ConfigService — reads/validates/saves ~/.bao/config.jsonc for the desktop app."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, ClassVar, TypeVar, cast

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

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


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None


_PROVIDER_COMMENT_LINES = (
    '// "provider-name": {',
    '//   "apiBase": "https://xxx",',
    '//   "apiKey": "sk-xxx",',
    '//   "extraHeaders": {},',
    '//   "type": "openai/anthropic/gemini"',
    "// }",
)


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _find_matching_brace(text: str, open_brace: int) -> int:
    normal = 0
    in_string = 1
    escape = 2
    line_comment = 3
    block_comment = 4

    state = normal
    depth = 0
    i = open_brace
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == normal:
            if ch == '"':
                state = in_string
            elif ch == "/" and nxt == "/":
                state = line_comment
                i += 1
            elif ch == "/" and nxt == "*":
                state = block_comment
                i += 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        elif state == in_string:
            if ch == "\\":
                state = escape
            elif ch == '"':
                state = normal
        elif state == escape:
            state = in_string
        elif state == line_comment:
            if ch == "\n":
                state = normal
        elif state == block_comment and ch == "*" and nxt == "/":
            state = normal
            i += 1

        i += 1

    return -1


def _inject_provider_comments(text: str) -> str:
    match = re.search(r'^(?P<indent>\s*)"providers"\s*:\s*\{', text, re.MULTILINE)
    if match is None:
        return text

    open_brace = match.end() - 1
    close_brace = _find_matching_brace(text, open_brace)
    if close_brace == -1:
        return text

    section = text[open_brace + 1 : close_brace]
    if re.search(r'^\s*//\s*"provider-name"\s*:\s*\{', section, re.MULTILINE):
        return text

    base_indent = match.group("indent")
    inner_indent = base_indent + "  "
    newline = _detect_newline(text)
    comment_block = newline.join(f"{inner_indent}{line}" for line in _PROVIDER_COMMENT_LINES)
    suffix = "" if section.strip() else newline + base_indent
    insertion = f"{newline}{comment_block}{suffix}"
    return text[: open_brace + 1] + insertion + text[open_brace + 1 :]


def _write_text_atomic(path: Path, content: str) -> None:
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            _ = handle.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


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
        from bao.runtime_diagnostics import get_runtime_diagnostics_store

        path = self._bootstrap_config_path()
        try:
            self._raw_text = path.read_text(encoding="utf-8")
            stripped = strip_comments(self._raw_text)
            raw_data = cast(object, json.loads(stripped))
            parsed_data = _as_dict(raw_data)
            if parsed_data is None:
                raise ValueError("Top-level config must be an object")
            self._data = parsed_data
            validated = RuntimeConfig.model_validate(self._data)
            self._apply_ui_defaults(validated)
            self._valid = True
            self._notify_state_changed()
            self.configLoaded.emit()
        except Exception as e:
            self._valid = False
            get_runtime_diagnostics_store().record_event(
                source="config",
                stage="load",
                message=f"Failed to load config: {e}",
                level="error",
                code="config_load_failed",
                retryable=False,
                details={"config_path": str(path)},
            )
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
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None:
            return []
        visible: list[dict[str, object]] = []
        for name, provider in providers.items():
            provider_dict = _as_dict(provider)
            if provider_dict is None:
                continue
            visible.append(
                {
                    "name": name,
                    "type": _as_str(provider_dict.get("type", "")),
                    "apiKey": _as_str(provider_dict.get("apiKey", "")),
                    "apiBase": _as_str(provider_dict.get("apiBase", "")),
                }
            )
        return visible

    @_typed_slot(result="QVariant")
    def exportData(self) -> dict[str, object]:
        return copy.deepcopy(self._data)

    @_typed_slot(result=str)
    def getConfigFilePath(self) -> str:
        return str(self._resolved_config_path())

    @_typed_slot()
    def openConfigDirectory(self) -> None:
        config_path = self._resolved_config_path()
        _ = QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_path.parent)))

    @_typed_slot(str, result=bool)
    def removeProvider(self, name: str) -> bool:
        """Remove a provider by name. Rewrites the providers object."""
        providers = _as_dict(self._data.get("providers", {}))
        if providers is None or name not in providers:
            return False
        return self.save(
            {"providers": {key: value for key, value in providers.items() if key != name}}
        )

    @_typed_slot("QVariantMap", result=bool)
    def save(self, changes: dict[str, object]) -> bool:
        """Apply *changes* (dotpath -> value) and write back preserving comments."""
        if self._config_path is None:
            self.saveError.emit("Config path not set — call load() first")
            return False

        changes = self._normalize_changes(changes)

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
        if "providers" in changes:
            result = _inject_provider_comments(result)
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
            _write_text_atomic(self._config_path, result)
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

    def _normalize_changes(self, changes: dict[str, object]) -> dict[str, object]:
        normalized = dict(changes)
        provider_entries = _as_list(normalized.get("providers"))
        if provider_entries is None:
            return normalized

        providers: dict[str, object] = {}
        for entry in provider_entries:
            entry_dict = _as_dict(entry)
            if entry_dict is None:
                continue
            name = _as_str(entry_dict.get("name", "")).strip()
            value = _as_dict(entry_dict.get("value"))
            if not name or value is None:
                continue
            providers[name] = value
        normalized["providers"] = providers
        return normalized

    def _notify_state_changed(self) -> None:
        """Emit stateChanged so QML re-evaluates isValid / needsSetup."""
        self.stateChanged.emit()

    def _apply_ui_defaults(self, validated: RuntimeConfig) -> None:
        ui_node = _as_dict(self._data.get("ui"))
        if ui_node is None:
            ui_node = {}
            self._data["ui"] = ui_node

        update_node = _as_dict(ui_node.get("update"))
        if update_node is None:
            update_node = {}
            ui_node["update"] = update_node

        defaults = validated.ui.update
        _ = update_node.setdefault("enabled", defaults.enabled)
        _ = update_node.setdefault("autoCheck", defaults.auto_check)
        _ = update_node.setdefault("channel", defaults.channel)
        _ = update_node.setdefault("feedUrl", defaults.feed_url)

    def _resolved_config_path(self) -> Path:
        if self._config_path is None:
            from bao.config.loader import get_config_path

            self._config_path = get_config_path()
        return self._config_path

    def _bootstrap_config_path(self) -> Path:
        path = self._resolved_config_path()
        if path.exists():
            return path

        from bao.config.loader import ensure_first_run, get_config_path

        _ = ensure_first_run()
        self._config_path = get_config_path()
        return self._config_path

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
