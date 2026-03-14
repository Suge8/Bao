from __future__ import annotations

import asyncio
import functools
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.backend.asyncio_runner import AsyncioRunner
from bao.config.onboarding import infer_language, write_heartbeat
from bao.heartbeat.service import HeartbeatService


def _tr(lang: str, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


def _normalized_path(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return str(Path(text).expanduser())


def _format_timestamp(value_ms: int | None) -> str:
    if not value_ms:
        return ""
    try:
        return datetime.fromtimestamp(value_ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def _preview_text(content: str, limit: int = 160) -> str:
    normalized = " ".join(part.strip() for part in content.splitlines() if part.strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _strip_line_prefix(text: str) -> str:
    normalized = text.strip()
    for prefix in ("- [ ] ", "- [x] ", "- [X] ", "- ", "* "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    parts = normalized.split(". ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1].strip()
    return normalized


def _heartbeat_preview(content: str, limit: int = 160) -> str:
    lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--") or line.endswith("-->"):
            continue
        if line.startswith("#"):
            continue
        cleaned = _strip_line_prefix(line)
        if cleaned:
            lines.append(cleaned)
    return _preview_text("\n".join(lines), limit=limit)


class HeartbeatBridgeService(QObject):
    stateChanged = Signal()
    busyChanged = Signal(bool)
    noticeChanged = Signal(str, bool)
    profileChanged = Signal()
    _refreshRequested = Signal()
    _refreshResult = Signal(object)
    _runResult = Signal(bool, str)

    def __init__(self, runner: AsyncioRunner, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._session_service: Any = None
        self._gateway_running = False
        self._lang = "en"
        self._current_profile_id = ""
        self._current_profile_name = ""
        self._local_heartbeat_file = Path.home() / ".bao" / "workspace" / "HEARTBEAT.md"
        self._live_heartbeat: HeartbeatService | None = None
        self._live_listener = lambda: self._refreshRequested.emit()
        self._busy = False
        self._notice_text = ""
        self._notice_success = True
        self._snapshot: dict[str, Any] = self._empty_snapshot()

        self._refreshRequested.connect(self.refresh)
        self._refreshResult.connect(self._handle_refresh_result)
        self._runResult.connect(self._handle_run_result)

    @Property(str, notify=profileChanged)
    def currentProfileId(self) -> str:
        return self._current_profile_id

    @Property(str, notify=profileChanged)
    def currentProfileName(self) -> str:
        return self._current_profile_name

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=noticeChanged)
    def noticeText(self) -> str:
        return self._notice_text

    @Property(bool, notify=noticeChanged)
    def noticeSuccess(self) -> bool:
        return self._notice_success

    @Property(str, notify=stateChanged)
    def heartbeatFilePath(self) -> str:
        return str(self._snapshot.get("heartbeat_file", ""))

    @Property(bool, notify=stateChanged)
    def heartbeatFileExists(self) -> bool:
        return bool(self._snapshot.get("heartbeat_file_exists", False))

    @Property(str, notify=stateChanged)
    def heartbeatPreview(self) -> str:
        return str(self._snapshot.get("heartbeat_preview", ""))

    @Property(bool, notify=stateChanged)
    def enabled(self) -> bool:
        return bool(self._snapshot.get("enabled", False))

    @Property(str, notify=stateChanged)
    def intervalText(self) -> str:
        return str(self._snapshot.get("interval_text", ""))

    @Property(str, notify=stateChanged)
    def lastCheckedText(self) -> str:
        return str(self._snapshot.get("last_checked_text", ""))

    @Property(str, notify=stateChanged)
    def lastDecisionLabel(self) -> str:
        return str(self._snapshot.get("last_decision_label", ""))

    @Property(str, notify=stateChanged)
    def lastError(self) -> str:
        return str(self._snapshot.get("last_error", ""))

    @Property(bool, notify=stateChanged)
    def canRunNow(self) -> bool:
        return self._run_now_state()[0]

    @Property(str, notify=stateChanged)
    def runNowBlockedReason(self) -> str:
        return self._run_now_state()[1]

    def supervisorSnapshot(self) -> dict[str, Any]:
        live = self._effective_live()
        live_status = live.status() if live is not None else {}
        snapshot = dict(self._snapshot)
        snapshot["running"] = bool(live_status.get("running", False))
        snapshot["enabled"] = bool(live_status.get("enabled", snapshot.get("enabled", False)))
        snapshot["last_checked_at_ms"] = live_status.get(
            "last_checked_at_ms",
            snapshot.get("last_checked_at_ms"),
        )
        snapshot["last_run_at_ms"] = live_status.get(
            "last_run_at_ms",
            snapshot.get("last_run_at_ms"),
        )
        snapshot["last_decision"] = str(
            live_status.get("last_decision", snapshot.get("last_decision", ""))
            or ""
        )
        return snapshot

    @Slot(object)
    def setSessionService(self, service: object) -> None:
        self._session_service = service

    @Slot(str, str)
    def setProfileInfo(self, profile_id: str, profile_name: str) -> None:
        next_profile_id = profile_id.strip()
        next_profile_name = profile_name.strip()
        if (
            self._current_profile_id == next_profile_id
            and self._current_profile_name == next_profile_name
        ):
            return
        self._current_profile_id = next_profile_id
        self._current_profile_name = next_profile_name
        self.profileChanged.emit()

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        normalized = "zh" if lang == "zh" else "en"
        if self._lang == normalized:
            return
        self._lang = normalized
        self.refresh()

    @Slot(str)
    def setLocalHeartbeatFilePath(self, path: str) -> None:
        normalized = _normalized_path(path)
        if not normalized:
            return
        if _normalized_path(self._local_heartbeat_file) == normalized:
            self.refresh()
            return
        self._local_heartbeat_file = Path(normalized)
        self.refresh()

    @Slot(object)
    def setLiveHeartbeatService(self, service: object) -> None:
        next_service = service if isinstance(service, HeartbeatService) else None
        if self._live_heartbeat is next_service:
            return
        if self._live_heartbeat is not None:
            self._live_heartbeat.remove_change_listener(self._live_listener)
        self._live_heartbeat = next_service
        if self._live_heartbeat is not None:
            self._live_heartbeat.add_change_listener(self._live_listener)
        self.refresh()

    @Slot(bool)
    def setGatewayRunning(self, running: bool) -> None:
        self._gateway_running = bool(running)
        self.stateChanged.emit()

    @Slot()
    def refresh(self) -> None:
        future = self._submit_safe(self._refresh_snapshot())
        if future is None:
            return
        future.add_done_callback(self._on_refresh_done)

    @Slot()
    def runNow(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        future = self._submit_safe(self._run_now())
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_run_done)

    @Slot()
    def openHeartbeatSession(self) -> None:
        if self._session_service is None:
            return
        select_session = getattr(self._session_service, "selectSession", None)
        if callable(select_session):
            select_session("heartbeat")

    @Slot()
    def openHeartbeatFile(self) -> None:
        try:
            heartbeat_file = self._ensure_local_heartbeat_file()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(heartbeat_file))):
                self._set_notice(
                    _tr(
                        self._lang,
                        "无法打开检查说明文件，请稍后重试",
                        "Unable to open the check instructions right now",
                    ),
                    False,
                )
                return
            self.refresh()
        except Exception as exc:
            self._set_notice(str(exc), False)

    def _submit_safe(self, coro: Any) -> Any:
        try:
            return self._runner.submit(coro)
        except RuntimeError:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            self._set_notice("Async runner unavailable", False)
            return None

    async def _run_user_io(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        call = functools.partial(fn, *args, **kwargs)
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_user_io(call)
        return await asyncio.to_thread(call)

    def _heartbeat_workspace(self) -> Path:
        return self._local_heartbeat_file.parent

    def _heartbeat_lang(self, workspace: Path) -> str:
        if (workspace / "INSTRUCTIONS.md").exists():
            return infer_language(workspace)
        return self._lang

    def _ensure_local_heartbeat_file(self) -> Path:
        workspace = self._heartbeat_workspace()
        workspace.mkdir(parents=True, exist_ok=True)
        if not self._local_heartbeat_file.exists():
            write_heartbeat(workspace, self._heartbeat_lang(workspace))
        if not self._local_heartbeat_file.exists():
            raise FileNotFoundError("HEARTBEAT.md not created")
        return self._local_heartbeat_file

    def _file_matches_current_profile(self, service: HeartbeatService | None) -> bool:
        if service is None:
            return False
        return _normalized_path(service.heartbeat_file) == _normalized_path(self._local_heartbeat_file)

    def _effective_live(self) -> HeartbeatService | None:
        return self._live_heartbeat if self._file_matches_current_profile(self._live_heartbeat) else None

    def _missing_file_reason(self) -> str:
        return _tr(
            self._lang,
            "还没有设置自动检查说明，先补充你希望 Bao 定期查看的事项",
            "Set up automatic check instructions before running this check",
        )

    def _gateway_not_ready_reason(self) -> str:
        return _tr(
            self._lang,
            "请先启动当前空间的网关，再开始自动检查",
            "Start the gateway for this space before running an automatic check",
        )

    def _switching_profile_reason(self) -> str:
        return _tr(
            self._lang,
            "正在切换到当前空间，请稍后再试",
            "Switching to the current space. Try again in a moment",
        )

    def _run_notice(self, decision: str, response: str | None) -> tuple[bool, str]:
        if decision == "missing":
            return False, self._missing_file_reason()
        if decision == "skip":
            return True, _tr(self._lang, "这次检查没有发现需要 Bao 处理的新任务", "No new tasks found")
        if decision == "run" and isinstance(response, str) and response.strip():
            return True, _tr(self._lang, "已开始处理这次检查发现的任务", "Tasks from this check are now running")
        return True, _tr(self._lang, "自动检查已完成", "Automatic check completed")

    def _run_now_state(self) -> tuple[bool, str]:
        if not self._local_heartbeat_file.exists():
            return False, self._missing_file_reason()
        live = self._effective_live()
        if self._live_heartbeat is not None and live is None:
            return False, self._switching_profile_reason()
        if not self._gateway_running or live is None:
            return False, self._gateway_not_ready_reason()
        return True, ""

    def _empty_snapshot(self) -> dict[str, Any]:
        return {
            "heartbeat_file": str(self._local_heartbeat_file),
            "heartbeat_file_exists": False,
            "heartbeat_preview": "",
            "enabled": False,
            "interval_text": "",
            "last_checked_text": "",
            "last_decision_label": "",
            "last_error": "",
        }

    def _decision_label(self, value: str) -> str:
        if value == "run":
            return _tr(self._lang, "发现任务", "Tasks found")
        if value == "skip":
            return _tr(self._lang, "无需执行", "Nothing to do")
        if value == "missing":
            return _tr(self._lang, "缺少 HEARTBEAT.md", "Missing HEARTBEAT.md")
        return ""

    def _interval_text(self, interval_s: int | None) -> str:
        seconds = int(interval_s or 0)
        if seconds <= 0:
            return ""
        minutes, remainder = divmod(seconds, 60)
        if remainder == 0 and minutes > 0:
            if minutes < 60:
                return _tr(self._lang, f"每 {minutes} 分钟", f"Every {minutes}m")
            hours, minutes = divmod(minutes, 60)
            if minutes == 0:
                return _tr(self._lang, f"每 {hours} 小时", f"Every {hours}h")
            return _tr(self._lang, f"每 {hours} 小时 {minutes} 分钟", f"Every {hours}h {minutes}m")
        return _tr(self._lang, f"每 {seconds} 秒", f"Every {seconds}s")

    async def _refresh_snapshot(self) -> dict[str, Any]:
        heartbeat_file = self._local_heartbeat_file
        content = ""
        if heartbeat_file.exists():
            content = await self._run_user_io(heartbeat_file.read_text, encoding="utf-8")
        live = self._effective_live()
        status = live.status() if live is not None else {}
        return {
            "heartbeat_file": str(heartbeat_file),
            "heartbeat_file_exists": heartbeat_file.exists(),
            "heartbeat_preview": _heartbeat_preview(content),
            "enabled": bool(status.get("enabled", False)),
            "interval_text": self._interval_text(status.get("interval_s")),
            "last_checked_text": _format_timestamp(status.get("last_checked_at_ms")),
            "last_decision_label": self._decision_label(str(status.get("last_decision", ""))),
            "last_error": str(status.get("last_error", "") or ""),
        }

    async def _run_now(self) -> tuple[bool, str]:
        ok, blocked_reason = self._run_now_state()
        if not ok:
            return False, blocked_reason
        live = self._effective_live()
        assert live is not None
        response = await live.trigger_now()
        status = live.status()
        last_error = str(status.get("last_error", "") or "").strip()
        if last_error:
            return False, last_error
        decision = str(status.get("last_decision", "") or "").strip()
        return self._run_notice(decision, response)

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busyChanged.emit(busy)

    def _set_notice(self, message: str, ok: bool) -> None:
        self._notice_text = message.strip()
        self._notice_success = ok
        self.noticeChanged.emit(self._notice_text, ok)

    def _on_refresh_done(self, future: Any) -> None:
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            self._refreshResult.emit(self._empty_snapshot())
            self._set_notice(str(exc), False)
            return
        self._refreshResult.emit(future.result())

    def _handle_refresh_result(self, payload: object) -> None:
        self._snapshot = dict(payload) if isinstance(payload, dict) else self._empty_snapshot()
        self.stateChanged.emit()

    def _on_run_done(self, future: Any) -> None:
        self._set_busy(False)
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            self._runResult.emit(False, str(exc))
            return
        ok, message = future.result()
        self._runResult.emit(ok, message)

    def _handle_run_result(self, ok: bool, message: str) -> None:
        self._set_notice(message, ok)
        self.refresh()
