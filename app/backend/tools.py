from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.config import ConfigService
from bao.agent.capability_registry import build_capability_registry_snapshot
from bao.agent.tool_catalog import ToolCatalog
from bao.agent.tool_probe_cache import delete_probe_result, load_probe_results, save_probe_result
from bao.agent.tools.mcp import probe_mcp_server
from bao.config.schema import MCPServerConfig
from bao.runtime_diagnostics import get_runtime_diagnostics_store


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    return None


def _as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


class ToolsService(QObject):
    changed: ClassVar[Signal] = Signal()
    busyChanged: ClassVar[Signal] = Signal()
    errorChanged: ClassVar[Signal] = Signal(str)
    operationFinished: ClassVar[Signal] = Signal(str, bool)

    _runnerResult: ClassVar[Signal] = Signal(str, bool, str, object)

    def __init__(
        self,
        runner: AsyncioRunner,
        config_service: ConfigService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._config_service = config_service
        self._catalog = ToolCatalog()
        self._runtime_diagnostics = get_runtime_diagnostics_store()
        self._probe_cache_dir = self._resolve_probe_cache_dir()
        self._config_data: dict[str, object] = {}
        self._query = ""
        self._source_filter = "all"
        self._busy = False
        self._busy_count = 0
        self._error = ""
        self._items: list[dict[str, object]] = []
        self._selected_id = ""
        self._selected_item: dict[str, object] = {}
        self._overview: dict[str, object] = {}
        self._probe_results: dict[str, dict[str, object]] = load_probe_results(self._probe_cache_dir)
        _ = self._runnerResult.connect(self._handle_runner_result)

    @Property(str, notify=changed)
    def query(self) -> str:
        return self._query

    @Property(str, notify=changed)
    def sourceFilter(self) -> str:
        return self._source_filter

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._error

    @Property(list, notify=changed)
    def items(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._items]

    @Property(dict, notify=changed)
    def selectedItem(self) -> dict[str, object]:
        return dict(self._selected_item)

    @Property(str, notify=changed)
    def selectedItemId(self) -> str:
        return self._selected_id

    @Property(dict, notify=changed)
    def overview(self) -> dict[str, object]:
        return dict(self._overview)

    @Slot("QVariant")
    def setConfigData(self, data: object) -> None:
        next_data = _as_dict(data) or {}
        self._config_data = dict(next_data)
        self._reload_probe_cache()
        self._refresh()

    @Slot(str)
    def setQuery(self, value: str) -> None:
        next_value = value.strip()
        if next_value == self._query:
            return
        self._query = next_value
        self._refresh()

    @Slot(str)
    def setSourceFilter(self, value: str) -> None:
        next_value = value if value in {"all", "builtin", "mcp", "attention"} else "all"
        if next_value == self._source_filter:
            return
        self._source_filter = next_value
        self._refresh()

    @Slot(str)
    def selectItem(self, item_id: str) -> None:
        target = next((item for item in self._items if item.get("id") == item_id), None)
        if target is None:
            return
        self._selected_id = item_id
        self._selected_item = dict(target)
        self.changed.emit()

    @Slot("QVariant", result=bool)
    def saveConfig(self, changes: object) -> bool:
        change_map = _as_dict(changes)
        if change_map is None:
            self._reject("Invalid config payload.")
            return False
        return self._save_patch(change_map, success_code="saved", failure_code="Save failed")

    @Slot("QVariant", result=bool)
    def saveMcpServer(self, payload: object) -> bool:
        data = _as_dict(payload)
        if data is None:
            self._reject("Invalid MCP server payload.")
            return False
        try:
            previous_name, next_name, server_value = self._normalize_server_payload(data)
        except ValueError as exc:
            self._reject(str(exc))
            return False

        current_servers = self._current_mcp_servers()
        if next_name in current_servers and next_name != previous_name:
            self._reject(f"MCP server already exists: {next_name}")
            return False
        if previous_name and previous_name != next_name:
            current_servers.pop(previous_name, None)
            self._probe_results.pop(previous_name, None)
        current_servers[next_name] = server_value
        if not self._save_patch(
            {"tools.mcpServers": current_servers},
            success_code="saved",
            failure_code="Save failed",
        ):
            return False
        if previous_name and previous_name != next_name:
            delete_probe_result(self._probe_cache_dir, previous_name)
        self._schedule_probe(next_name, server_value)
        return True

    @Slot(str, result=bool)
    def deleteMcpServer(self, name: str) -> bool:
        target = name.strip()
        if not target:
            return False
        current_servers = self._current_mcp_servers()
        if target not in current_servers:
            return False
        current_servers.pop(target, None)
        self._probe_results.pop(target, None)
        delete_probe_result(self._probe_cache_dir, target)
        return self._save_patch(
            {"tools.mcpServers": current_servers},
            success_code="deleted",
            failure_code="Delete failed",
        )

    @Slot(str)
    def testMcpServer(self, name: str) -> None:
        target = name.strip()
        if not target:
            return
        current_servers = self._current_mcp_servers()
        raw_cfg = current_servers.get(target)
        cfg_dict = _as_dict(raw_cfg)
        if cfg_dict is None:
            message = f"Unknown MCP server: {target}"
            self._set_error(message)
            self.operationFinished.emit(message, False)
            return
        self._submit_task("probe_server", self._probe_server(target, cfg_dict))

    @Slot("QVariant")
    def probeMcpServerPayload(self, payload: object) -> None:
        data = _as_dict(payload)
        if data is None:
            self._reject("Invalid MCP server payload.")
            return
        try:
            _previous_name, next_name, server_value = self._normalize_server_payload(data)
        except ValueError as exc:
            self._reject(str(exc))
            return
        self._submit_task("probe_server", self._probe_server(next_name, server_value))

    def _current_mcp_servers(self) -> dict[str, object]:
        return dict(_as_dict(self._config_service.get("tools.mcpServers", {})) or {})

    def _refresh(self) -> None:
        snapshot = build_capability_registry_snapshot(
            catalog=self._catalog,
            config_data=self._config_data,
            probe_results=self._probe_results,
            query=self._query.lower(),
            source_filter=self._source_filter,
            selected_id=self._selected_id,
            diagnostics_snapshot=self._runtime_diagnostics.snapshot(max_events=0, max_log_lines=0),
        )
        self._overview = dict(snapshot.overview)
        self._items = [dict(item) for item in snapshot.items]
        self._selected_id = snapshot.selected_id
        self._selected_item = dict(snapshot.selected_item)
        self.changed.emit()

    def _submit_task(self, kind: str, coro: Coroutine[Any, Any, Any]) -> None:
        try:
            future = self._runner.submit(coro)
        except RuntimeError:
            coro.close()
            self._set_error("Asyncio runner is not available.")
            return
        self._set_busy(True)
        future.add_done_callback(lambda f, task_kind=kind: self._emit_runner_result(task_kind, f))

    def _save_patch(
        self, patch: dict[str, object], *, success_code: str, failure_code: str
    ) -> bool:
        ok = self._config_service.save(patch)
        if not ok:
            self.operationFinished.emit(failure_code, False)
            return False
        self.setConfigData(self._config_service.exportData())
        self.operationFinished.emit(success_code, True)
        return True

    def _reject(self, message: str) -> None:
        self._set_error(message)
        self.operationFinished.emit(message, False)

    def _emit_runner_result(self, kind: str, future: Any) -> None:
        try:
            payload = future.result()
            self._runnerResult.emit(kind, True, "", payload)
        except asyncio.CancelledError:
            self._runnerResult.emit(kind, False, "cancelled", None)
        except Exception as exc:
            self._runnerResult.emit(kind, False, str(exc), None)

    @Slot(str, bool, str, object)
    def _handle_runner_result(self, kind: str, ok: bool, message: str, payload: object) -> None:
        self._set_busy(False)
        if kind != "probe_server":
            return
        if not ok:
            self._set_error(message)
            self.operationFinished.emit(message, False)
            return
        result = _as_dict(payload) or {}
        name = _as_str(result.get("serverName", ""))
        if name:
            self._probe_results[name] = dict(
                save_probe_result(self._probe_cache_dir, name, dict(result))
            )
        self._refresh()
        self.operationFinished.emit(
            "probe_ok"
            if bool(result.get("canConnect"))
            else _as_str(result.get("error", "probe_failed")),
            bool(result.get("canConnect")),
        )

    async def _probe_server(self, name: str, config_value: dict[str, object]) -> dict[str, object]:
        cfg = MCPServerConfig.model_validate(config_value)
        return await probe_mcp_server(name, cfg)

    def _schedule_probe(self, name: str, config_value: dict[str, object]) -> None:
        self._submit_task("probe_server", self._probe_server(name, config_value))

    def _normalize_server_payload(
        self, payload: dict[str, object]
    ) -> tuple[str, str, dict[str, object]]:
        previous_name = _as_str(payload.get("previousName", "")).strip()
        next_name = _as_str(payload.get("name", "")).strip()
        if not next_name:
            raise ValueError("Server name is required.")

        transport = _as_str(payload.get("transport", "stdio"), "stdio").strip().lower()
        if transport not in {"stdio", "http"}:
            transport = "stdio"

        command = _as_str(payload.get("command", "")).strip()
        url = _as_str(payload.get("url", "")).strip()
        if transport == "stdio" and not command:
            raise ValueError("Command is required for stdio MCP servers.")
        if transport == "http" and not url:
            raise ValueError("URL is required for HTTP MCP servers.")

        server_value: dict[str, object] = {
            "command": command if transport == "stdio" else "",
            "args": self._parse_multiline_list(_as_str(payload.get("argsText", ""))),
            "env": self._parse_key_values(_as_str(payload.get("envText", "")), separators=("=",)),
            "url": url if transport == "http" else "",
            "headers": self._parse_key_values(
                _as_str(payload.get("headersText", "")), separators=(":", "=")
            ),
            "toolTimeoutSeconds": max(1, self._coerce_int(payload.get("toolTimeoutSeconds"), 30)),
            "maxTools": self._normalize_optional_int(payload.get("maxTools")),
            "slimSchema": payload.get("slimSchema")
            if isinstance(payload.get("slimSchema"), bool)
            else None,
        }
        return previous_name, next_name, server_value

    @staticmethod
    def _parse_multiline_list(value: str) -> list[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]

    @staticmethod
    def _parse_key_values(value: str, *, separators: tuple[str, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_line in value.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            pair: tuple[str, str] | None = None
            for separator in separators:
                if separator in line:
                    left, right = line.split(separator, 1)
                    pair = (left.strip(), right.strip())
                    break
            if pair is None or not pair[0]:
                raise ValueError(f"Invalid key/value line: {raw_line}")
            result[pair[0]] = pair[1]
        return result

    @staticmethod
    def _coerce_int(value: object, default: int) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                try:
                    return int(stripped)
                except ValueError:
                    return default
        return default

    def _normalize_optional_int(self, value: object) -> int | None:
        coerced = self._coerce_int(value, 0)
        return coerced if coerced > 0 else None

    def _resolve_probe_cache_dir(self) -> Path:
        config_path = self._config_service.getConfigFilePath()
        return Path(config_path).expanduser().resolve().parent if config_path else Path.home() / ".bao"

    def _reload_probe_cache(self) -> None:
        self._probe_cache_dir = self._resolve_probe_cache_dir()
        cached = load_probe_results(self._probe_cache_dir)
        current_servers = set(self._current_mcp_servers())
        self._probe_results = {
            name: dict(result) for name, result in cached.items() if not current_servers or name in current_servers
        }

    def _set_busy(self, active: bool) -> None:
        self._busy_count = max(0, self._busy_count + (1 if active else -1))
        next_busy = self._busy_count > 0
        if next_busy == self._busy:
            return
        self._busy = next_busy
        self.busyChanged.emit()

    def _set_error(self, message: str) -> None:
        if message == self._error:
            return
        self._error = message
        self.errorChanged.emit(message)
