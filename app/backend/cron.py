from __future__ import annotations

import asyncio
import functools
from datetime import datetime
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from app.backend.asyncio_runner import AsyncioRunner
from bao.config.loader import get_data_dir
from bao.cron.service import CronService
from bao.cron.types import CronJob, CronSchedule

_DRAFT_PREVIEW_ID = "__draft__"


def _format_timestamp(value_ms: int | None) -> str:
    if not value_ms:
        return ""
    try:
        return datetime.fromtimestamp(value_ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def _format_at_input(value_ms: int | None) -> str:
    if not value_ms:
        return ""
    try:
        return datetime.fromtimestamp(value_ms / 1000).strftime("%Y-%m-%dT%H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def _parse_at_input(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    normalized = text.replace(" ", "T") if "T" not in text else text
    dt = datetime.fromisoformat(normalized)
    return int(dt.timestamp() * 1000)


def _tr(lang: str, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


def _schedule_summary(job: CronJob, lang: str) -> str:
    schedule = job.schedule
    if schedule.kind == "at":
        if schedule.at_ms:
            return _tr(
                lang,
                f"单次 · {_format_timestamp(schedule.at_ms)}",
                f"One-shot · {_format_timestamp(schedule.at_ms)}",
            )
        return _tr(lang, "单次执行", "One-shot")
    if schedule.kind == "every":
        minutes = int((schedule.every_ms or 0) / 60000)
        if minutes <= 0:
            return _tr(lang, "循环执行", "Repeats")
        if minutes < 60:
            return _tr(lang, f"每 {minutes} 分钟", f"Every {minutes}m")
        hours, remainder = divmod(minutes, 60)
        if remainder == 0:
            return _tr(lang, f"每 {hours} 小时", f"Every {hours}h")
        return _tr(lang, f"每 {hours} 小时 {remainder} 分钟", f"Every {hours}h {remainder}m")
    expr = schedule.expr or ""
    if schedule.tz:
        return f"{expr} · {schedule.tz}" if expr else schedule.tz
    return expr or _tr(lang, "Cron 表达式", "Cron")


def _status_key(job: CronJob) -> str:
    if not job.enabled:
        return "disabled"
    if job.state.last_status == "error":
        return "error"
    if job.state.next_run_at_ms:
        return "scheduled"
    if job.state.last_status == "ok":
        return "idle_ok"
    return "draft"


def _status_label(job: CronJob, lang: str) -> str:
    key = _status_key(job)
    if key == "disabled":
        return _tr(lang, "已停用", "Disabled")
    if key == "error":
        return _tr(lang, "异常", "Error")
    if key == "scheduled":
        return _tr(lang, "已调度", "Scheduled")
    if key == "idle_ok":
        return _tr(lang, "已就绪", "Ready")
    return _tr(lang, "未安排", "Not scheduled")


def _last_result_text(job: CronJob, lang: str) -> str:
    if job.state.last_status == "error":
        return (
            _tr(
                lang,
                f"失败 · {_format_timestamp(job.state.last_run_at_ms)}",
                f"Failed · {_format_timestamp(job.state.last_run_at_ms)}",
            )
            if job.state.last_run_at_ms
            else _tr(lang, "失败", "Failed")
        )
    if job.state.last_status == "ok":
        return (
            _tr(
                lang,
                f"成功 · {_format_timestamp(job.state.last_run_at_ms)}",
                f"OK · {_format_timestamp(job.state.last_run_at_ms)}",
            )
            if job.state.last_run_at_ms
            else _tr(lang, "成功", "OK")
        )
    if not job.state.last_run_at_ms:
        return _tr(lang, "从未执行", "Never run")
    return _format_timestamp(job.state.last_run_at_ms)


def _serialize_job(job: CronJob, lang: str) -> dict[str, Any]:
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule_kind": job.schedule.kind,
        "schedule_summary": _schedule_summary(job, lang),
        "schedule": {
            "kind": job.schedule.kind,
            "at_ms": job.schedule.at_ms,
            "every_ms": job.schedule.every_ms,
            "expr": job.schedule.expr or "",
            "tz": job.schedule.tz or "",
        },
        "message": job.payload.message,
        "deliver": job.payload.deliver,
        "channel": job.payload.channel or "",
        "target": job.payload.to or "",
        "delete_after_run": job.delete_after_run,
        "next_run_at_ms": job.state.next_run_at_ms,
        "next_run_text": _format_timestamp(job.state.next_run_at_ms),
        "last_run_at_ms": job.state.last_run_at_ms,
        "last_run_text": _format_timestamp(job.state.last_run_at_ms),
        "last_status": job.state.last_status or "",
        "last_error": job.state.last_error or "",
        "last_result_text": _last_result_text(job, lang),
        "status_key": _status_key(job),
        "status_label": _status_label(job, lang),
        "session_key": f"cron:{job.id}",
        "created_at_ms": job.created_at_ms,
        "updated_at_ms": job.updated_at_ms,
    }


def _empty_draft() -> dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "enabled": True,
        "schedule_kind": "every",
        "at_input": "",
        "every_minutes": "60",
        "cron_expr": "0 9 * * *",
        "timezone": "",
        "message": "",
        "deliver": False,
        "channel": "",
        "target": "",
        "delete_after_run": False,
    }


def _draft_from_task(task: dict[str, Any]) -> dict[str, Any]:
    raw_schedule = task.get("schedule")
    schedule: dict[str, Any] = {}
    if isinstance(raw_schedule, dict):
        schedule = {str(key): value for key, value in raw_schedule.items()}
    return {
        "id": str(task.get("id", "")),
        "name": str(task.get("name", "")),
        "enabled": bool(task.get("enabled", True)),
        "schedule_kind": str(task.get("schedule_kind", "every")),
        "at_input": _format_at_input(schedule.get("at_ms")),
        "every_minutes": str(max(1, int((schedule.get("every_ms") or 60000) / 60000))),
        "cron_expr": str(schedule.get("expr", "") or ""),
        "timezone": str(schedule.get("tz", "") or ""),
        "message": str(task.get("message", "")),
        "deliver": bool(task.get("deliver", False)),
        "channel": str(task.get("channel", "")),
        "target": str(task.get("target", "")),
        "delete_after_run": bool(task.get("delete_after_run", False)),
    }


def _draft_schedule_summary(draft: dict[str, Any], lang: str) -> str:
    kind = str(draft.get("schedule_kind", "every") or "every")
    if kind == "at":
        at_input = str(draft.get("at_input", "")).strip()
        return at_input or _tr(lang, "单次执行", "One-shot")
    if kind == "cron":
        expr = str(draft.get("cron_expr", "")).strip()
        tz = str(draft.get("timezone", "")).strip()
        if expr and tz:
            return f"{expr} · {tz}"
        return expr or _tr(lang, "高级规则", "Advanced")
    minutes_raw = str(draft.get("every_minutes", "")).strip()
    try:
        minutes = int(minutes_raw)
    except ValueError:
        minutes = 0
    if minutes <= 0:
        return _tr(lang, "循环执行", "Repeats")
    if minutes < 60:
        return _tr(lang, f"每 {minutes} 分钟", f"Every {minutes}m")
    hours, remainder = divmod(minutes, 60)
    if remainder == 0:
        return _tr(lang, f"每 {hours} 小时", f"Every {hours}h")
    return _tr(lang, f"每 {hours} 小时 {remainder} 分钟", f"Every {hours}h {remainder}m")


def _draft_preview_task(draft: dict[str, Any], lang: str) -> dict[str, Any]:
    enabled = bool(draft.get("enabled", True))
    return {
        "id": _DRAFT_PREVIEW_ID,
        "name": str(draft.get("name", "")).strip() or _tr(lang, "未命名任务", "Untitled task"),
        "enabled": enabled,
        "schedule_kind": str(draft.get("schedule_kind", "every") or "every"),
        "schedule": {
            "kind": str(draft.get("schedule_kind", "every") or "every"),
            "at_ms": None,
            "every_ms": None,
            "expr": str(draft.get("cron_expr", "") or ""),
            "tz": str(draft.get("timezone", "") or ""),
        },
        "schedule_summary": _draft_schedule_summary(draft, lang),
        "message": str(draft.get("message", "")),
        "deliver": bool(draft.get("deliver", False)),
        "channel": str(draft.get("channel", "")),
        "target": str(draft.get("target", "")),
        "delete_after_run": bool(draft.get("delete_after_run", False)),
        "next_run_at_ms": None,
        "next_run_text": _tr(lang, "保存后生成", "Created after save"),
        "last_run_at_ms": None,
        "last_run_text": "",
        "last_status": "",
        "last_error": "",
        "last_result_text": _tr(lang, "尚未保存", "Not saved yet"),
        "status_key": "draft",
        "status_label": _tr(lang, "新草稿", "New draft"),
        "session_key": "",
        "created_at_ms": None,
        "updated_at_ms": None,
        "is_draft": True,
    }


class CronTasksModel(QAbstractListModel):
    _ROLE_BASE = int(Qt.ItemDataRole.UserRole)
    _ROLE_NAMES = {
        _ROLE_BASE + 1: QByteArray(b"taskId"),
        _ROLE_BASE + 2: QByteArray(b"name"),
        _ROLE_BASE + 3: QByteArray(b"enabled"),
        _ROLE_BASE + 4: QByteArray(b"statusKey"),
        _ROLE_BASE + 5: QByteArray(b"statusLabel"),
        _ROLE_BASE + 6: QByteArray(b"scheduleSummary"),
        _ROLE_BASE + 7: QByteArray(b"nextRunText"),
        _ROLE_BASE + 8: QByteArray(b"lastResultText"),
        _ROLE_BASE + 9: QByteArray(b"lastError"),
        _ROLE_BASE + 10: QByteArray(b"sessionKey"),
        _ROLE_BASE + 11: QByteArray(b"isDraft"),
    }
    _FIELD_MAP = {
        _ROLE_BASE + 1: "id",
        _ROLE_BASE + 2: "name",
        _ROLE_BASE + 3: "enabled",
        _ROLE_BASE + 4: "status_key",
        _ROLE_BASE + 5: "status_label",
        _ROLE_BASE + 6: "schedule_summary",
        _ROLE_BASE + 7: "next_run_text",
        _ROLE_BASE + 8: "last_result_text",
        _ROLE_BASE + 9: "last_error",
        _ROLE_BASE + 10: "session_key",
        _ROLE_BASE + 11: "is_draft",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        field = self._FIELD_MAP.get(role)
        if field is None:
            return None
        return row.get(field)

    def roleNames(self) -> dict[int, QByteArray]:
        return dict(self._ROLE_NAMES)

    def reset_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()


class CronBridgeService(QObject):
    tasksChanged = Signal()
    selectedTaskChanged = Signal()
    draftChanged = Signal()
    busyChanged = Signal(bool)
    errorChanged = Signal(str)
    noticeChanged = Signal(str, bool)
    filtersChanged = Signal()
    _refreshRequested = Signal()
    _loadResult = Signal(bool, str, object)
    _saveResult = Signal(bool, str, str)
    _deleteResult = Signal(bool, str, str)
    _toggleResult = Signal(bool, str, str)
    _runResult = Signal(bool, str)

    def __init__(self, runner: AsyncioRunner, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._tasks_model = CronTasksModel(self)
        self._all_tasks: list[dict[str, Any]] = []
        self._projected_tasks: list[dict[str, Any]] = []
        self._selected_task_id = ""
        self._draft: dict[str, Any] = _empty_draft()
        self._draft_dirty = False
        self._busy = False
        self._last_error = ""
        self._notice_text = ""
        self._notice_success = True
        self._filter_query = ""
        self._status_filter = "all"
        self._session_service: Any = None
        self._gateway_running = False
        self._lang = "en"
        self._local_cron = CronService(get_data_dir() / "cron" / "jobs.json")
        self._live_cron: CronService | None = None
        self._local_listener = lambda: self._refreshRequested.emit()
        self._live_listener = lambda: self._refreshRequested.emit()
        self._local_cron.add_change_listener(self._local_listener)

        self._refreshRequested.connect(self.refresh)
        self._loadResult.connect(self._handle_load_result)
        self._saveResult.connect(self._handle_save_result)
        self._deleteResult.connect(self._handle_delete_result)
        self._toggleResult.connect(self._handle_toggle_result)
        self._runResult.connect(self._handle_run_result)

    @Property(QObject, constant=True)
    def tasksModel(self) -> CronTasksModel:
        return self._tasks_model

    @Property(int, notify=tasksChanged)
    def totalTaskCount(self) -> int:
        return len(self._all_tasks) + (1 if self.editingNewTask else 0)

    @Property(int, notify=tasksChanged)
    def visibleTaskCount(self) -> int:
        return len(self._projected_tasks)

    @Property(str, notify=selectedTaskChanged)
    def activeListItemId(self) -> str:
        draft_id = self._draft_id()
        if draft_id:
            return draft_id
        if self.editingNewTask:
            return _DRAFT_PREVIEW_ID
        return self._selected_task_id

    @Property(str, notify=selectedTaskChanged)
    def selectedTaskId(self) -> str:
        return self._selected_task_id

    @Property(bool, notify=selectedTaskChanged)
    def hasSelection(self) -> bool:
        return bool(self._current_saved_task_id())

    @Property(dict, notify=selectedTaskChanged)
    def selectedTask(self) -> dict[str, Any]:
        task = self._current_saved_task()
        return dict(task) if task is not None else {}

    @Property(dict, notify=draftChanged)
    def draft(self) -> dict[str, Any]:
        return dict(self._draft)

    @Property(bool, notify=draftChanged)
    def draftDirty(self) -> bool:
        return self._draft_dirty

    @Property(bool, notify=draftChanged)
    def hasDraft(self) -> bool:
        return bool(self._draft.get("id") or self._draft_dirty or self._draft.get("name"))

    @Property(bool, notify=draftChanged)
    def editingNewTask(self) -> bool:
        return self.hasDraft and not bool(self._draft.get("id"))

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._last_error

    @Property(str, notify=noticeChanged)
    def noticeText(self) -> str:
        return self._notice_text

    @Property(bool, notify=noticeChanged)
    def noticeSuccess(self) -> bool:
        return self._notice_success

    @Property(str, notify=filtersChanged)
    def filterQuery(self) -> str:
        return self._filter_query

    @Property(str, notify=filtersChanged)
    def statusFilter(self) -> str:
        return self._status_filter

    @Slot(object)
    def setSessionService(self, service: object) -> None:
        self._session_service = service

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        normalized = "zh" if lang == "zh" else "en"
        if self._lang == normalized:
            return
        self._lang = normalized
        self.refresh()

    @Slot(object)
    def setLiveCronService(self, service: object) -> None:
        next_service = service if isinstance(service, CronService) else None
        if self._live_cron is next_service:
            return
        if self._live_cron is not None:
            self._live_cron.remove_change_listener(self._live_listener)
        self._live_cron = next_service
        if self._live_cron is not None:
            self._live_cron.add_change_listener(self._live_listener)
        self.refresh()

    @Slot(bool)
    def setGatewayRunning(self, running: bool) -> None:
        self._gateway_running = bool(running)

    @Slot()
    def refresh(self) -> None:
        future = self._submit_safe(self._load_tasks())
        if future is None:
            return
        future.add_done_callback(self._on_load_done)

    @Slot(str)
    def selectTask(self, task_id: str) -> None:
        if task_id == _DRAFT_PREVIEW_ID:
            self.newDraft()
            return
        if task_id == self._selected_task_id:
            task = self._selected_task()
            draft_id = str(self._draft.get("id", "")).strip()
            if task is None or (draft_id == task_id and not self.editingNewTask):
                return
            self._draft = _draft_from_task(task)
            self._draft_dirty = False
            self._apply_projection()
            self.selectedTaskChanged.emit()
            self.draftChanged.emit()
            return
        self._selected_task_id = task_id
        task = self._selected_task()
        self._draft = _draft_from_task(task) if task else _empty_draft()
        self._draft_dirty = False
        self._apply_projection()
        self.selectedTaskChanged.emit()
        self.draftChanged.emit()

    @Slot()
    def newDraft(self) -> None:
        self._selected_task_id = ""
        self._draft = _empty_draft()
        self._draft_dirty = True
        self._apply_projection()
        self.selectedTaskChanged.emit()
        self.draftChanged.emit()

    @Slot()
    def duplicateSelected(self) -> None:
        task = self._selected_task()
        if not task:
            return
        self._selected_task_id = ""
        self._draft = _draft_from_task(task)
        self._draft["id"] = ""
        self._draft["name"] = f"{self._draft['name']} Copy".strip()
        self._draft_dirty = True
        self._apply_projection()
        self.selectedTaskChanged.emit()
        self.draftChanged.emit()

    @Slot(str, "QVariant")
    def updateDraftField(self, path: str, value: Any) -> None:
        parts = [part for part in path.split(".") if part]
        if not parts:
            return
        draft = dict(self._draft)
        node: dict[str, Any] = draft
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
            child = dict(child)
            node[part] = child
            node = child
        node[parts[-1]] = value
        self._draft = draft
        self._draft_dirty = True
        if self.editingNewTask:
            self._apply_projection()
        self.draftChanged.emit()

    @Slot(str)
    def setFilterQuery(self, query: str) -> None:
        normalized = query.strip()
        if self._filter_query == normalized:
            return
        self._filter_query = normalized
        self._apply_projection()

    @Slot(str)
    def setStatusFilter(self, value: str) -> None:
        normalized = value.strip() or "all"
        if self._status_filter == normalized:
            return
        self._status_filter = normalized
        self._apply_projection()

    @Slot()
    def saveDraft(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        future = self._submit_safe(self._save_draft())
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_save_done)

    @Slot()
    def deleteSelected(self) -> None:
        task = self._selected_task()
        if task is None or self._busy:
            return
        self._set_busy(True)
        future = self._submit_safe(self._delete_task(str(task.get("id", ""))))
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_delete_done)

    @Slot(bool)
    def setSelectedEnabled(self, enabled: bool) -> None:
        task = self._selected_task()
        if task is None or self._busy:
            return
        self._set_busy(True)
        future = self._submit_safe(self._toggle_task(str(task.get("id", "")), bool(enabled)))
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_toggle_done)

    @Slot()
    def runSelectedNow(self) -> None:
        task = self._selected_task()
        if task is None or self._busy:
            return
        self._set_busy(True)
        future = self._submit_safe(self._run_task_now(str(task.get("id", ""))))
        if future is None:
            self._set_busy(False)
            return
        future.add_done_callback(self._on_run_done)

    @Slot()
    def openSelectedSession(self) -> None:
        task = self._selected_task()
        if task is None or self._session_service is None:
            return
        select_session = getattr(self._session_service, "selectSession", None)
        if callable(select_session):
            select_session(str(task.get("session_key", "")))

    def _submit_safe(self, coro: Any) -> Any:
        try:
            return self._runner.submit(coro)
        except RuntimeError:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            self._set_error("Async runner unavailable")
            return None

    async def _run_user_io(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        call = functools.partial(fn, *args, **kwargs)
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_user_io(call)
        return await asyncio.to_thread(call)

    def _current_service(self) -> CronService:
        return self._live_cron or self._local_cron

    async def _load_tasks(self) -> list[dict[str, Any]]:
        jobs = await self._run_user_io(self._current_service().list_jobs, True)
        return [_serialize_job(job, self._lang) for job in jobs]

    async def _save_draft(self) -> tuple[str, str]:
        service = self._current_service()
        draft = dict(self._draft)
        name = str(draft.get("name", "")).strip()
        if not name:
            raise ValueError(_tr(self._lang, "任务名称不能为空", "Task name is required"))
        message = str(draft.get("message", "")).strip()
        if not message:
            raise ValueError(_tr(self._lang, "消息内容不能为空", "Message is required"))
        deliver = bool(draft.get("deliver", False))
        channel = str(draft.get("channel", "")).strip() or None
        target = str(draft.get("target", "")).strip() or None
        if deliver and (not channel or not target):
            raise ValueError(
                _tr(
                    self._lang,
                    "投递模式必须同时填写渠道和目标",
                    "Delivery requires both channel and target",
                )
            )
        schedule = self._schedule_from_draft(draft)
        task_id = str(draft.get("id", "")).strip()
        enabled = bool(draft.get("enabled", True))
        delete_after_run = bool(draft.get("delete_after_run", False))
        if task_id:
            job = await self._run_user_io(
                service.update_job,
                task_id,
                name=name,
                enabled=enabled,
                schedule=schedule,
                message=message,
                deliver=deliver,
                channel=channel,
                to=target,
                delete_after_run=delete_after_run,
            )
            if job is None:
                raise ValueError(_tr(self._lang, "任务不存在", "Task not found"))
            return job.id, _tr(self._lang, "任务已更新", "Task updated")
        job = await self._run_user_io(
            service.add_job,
            name,
            schedule,
            message,
            enabled,
            deliver,
            channel,
            target,
            delete_after_run,
        )
        return job.id, _tr(self._lang, "任务已创建", "Task created")

    async def _delete_task(self, task_id: str) -> tuple[str, bool]:
        removed = await self._run_user_io(self._current_service().remove_job, task_id)
        return task_id, bool(removed)

    async def _toggle_task(self, task_id: str, enabled: bool) -> tuple[str, bool]:
        job = await self._run_user_io(self._current_service().enable_job, task_id, enabled)
        return task_id, job is not None

    async def _run_task_now(self, task_id: str) -> bool:
        if not self._gateway_running or self._live_cron is None:
            raise ValueError(
                _tr(
                    self._lang,
                    "请先启动网关，再立即执行任务",
                    "Start the gateway to run a task now",
                )
            )
        return await self._live_cron.run_job(task_id, force=True)

    def _schedule_from_draft(self, draft: dict[str, Any]) -> CronSchedule:
        kind = str(draft.get("schedule_kind", "every") or "every")
        if kind == "at":
            at_value = _parse_at_input(str(draft.get("at_input", "")))
            if not at_value:
                raise ValueError(
                    _tr(
                        self._lang,
                        "单次任务必须填写执行时间",
                        "One-shot tasks need a date and time",
                    )
                )
            return CronSchedule(kind="at", at_ms=at_value)
        if kind == "every":
            minutes_raw = str(draft.get("every_minutes", "")).strip()
            try:
                minutes = int(minutes_raw)
            except ValueError as exc:
                raise ValueError(
                    _tr(
                        self._lang,
                        "循环间隔必须是整数分钟",
                        "Repeat interval must be a whole number of minutes",
                    )
                ) from exc
            if minutes <= 0:
                raise ValueError(
                    _tr(
                        self._lang,
                        "循环间隔必须大于 0",
                        "Repeat interval must be greater than zero",
                    )
                )
            return CronSchedule(kind="every", every_ms=minutes * 60_000)
        if kind == "cron":
            expr = str(draft.get("cron_expr", "")).strip()
            if not expr:
                raise ValueError(
                    _tr(self._lang, "Cron 表达式不能为空", "Cron expression is required")
                )
            tz = str(draft.get("timezone", "")).strip() or None
            return CronSchedule(kind="cron", expr=expr, tz=tz)
        raise ValueError(_tr(self._lang, "不支持的调度类型", "Unsupported schedule type"))

    def _selected_task(self) -> dict[str, Any] | None:
        for task in self._all_tasks:
            if str(task.get("id", "")) == self._selected_task_id:
                return task
        return None

    def _draft_id(self) -> str:
        return str(self._draft.get("id", "")).strip()

    def _current_saved_task_id(self) -> str:
        draft_id = self._draft_id()
        return draft_id or self._selected_task_id

    def _current_saved_task(self) -> dict[str, Any] | None:
        task_id = self._current_saved_task_id()
        for task in self._all_tasks:
            if str(task.get("id", "")) == task_id:
                return task
        return None

    def _first_saved_task(self) -> dict[str, Any] | None:
        return self._all_tasks[0] if self._all_tasks else None

    def _matches_filter(self, task: dict[str, Any]) -> bool:
        query = self._filter_query.lower()
        if query:
            haystack = " ".join(
                [
                    str(task.get("name", "")),
                    str(task.get("schedule_summary", "")),
                    str(task.get("message", "")),
                    str(task.get("channel", "")),
                    str(task.get("target", "")),
                ]
            ).lower()
            if query not in haystack:
                return False
        status_filter = self._status_filter
        if status_filter == "all":
            return True
        if status_filter == "enabled":
            return bool(task.get("enabled", False))
        if status_filter == "disabled":
            return not bool(task.get("enabled", False))
        if status_filter == "issues":
            return str(task.get("status_key", "")) == "error"
        if status_filter == "scheduled":
            return str(task.get("status_key", "")) == "scheduled"
        return True

    def _apply_projection(self) -> None:
        if not self.editingNewTask:
            current_task = self._current_saved_task()
            if current_task is None:
                current_task = self._first_saved_task()
                self._selected_task_id = str(current_task.get("id", "")) if current_task else ""
            if current_task is not None and self._draft_id() != str(current_task.get("id", "")):
                self._draft = _draft_from_task(current_task)
                self._draft_dirty = False
        projected = [task for task in self._all_tasks if self._matches_filter(task)]
        if self.editingNewTask:
            projected = [_draft_preview_task(self._draft, self._lang), *projected]
        self._projected_tasks = projected
        self._tasks_model.reset_rows(self._projected_tasks)
        self.tasksChanged.emit()
        self.filtersChanged.emit()
        self.selectedTaskChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busyChanged.emit(busy)

    def _set_error(self, message: str) -> None:
        text = message.strip()
        if self._last_error == text:
            return
        self._last_error = text
        self.errorChanged.emit(text)

    def _set_notice(self, message: str, ok: bool) -> None:
        self._notice_text = message.strip()
        self._notice_success = ok
        self.noticeChanged.emit(self._notice_text, ok)

    def _on_load_done(self, future: Any) -> None:
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            self._loadResult.emit(False, str(exc), [])
            return
        self._loadResult.emit(True, "", future.result())

    def _handle_load_result(self, ok: bool, error: str, payload: object) -> None:
        if not ok:
            self._set_error(error)
            self._set_notice(error, False)
            return
        items = payload if isinstance(payload, list) else []
        self._all_tasks = [dict(item) for item in items if isinstance(item, dict)]
        if self._selected_task_id and self._selected_task() is None:
            self._selected_task_id = ""
        if not self._selected_task_id and self._all_tasks and not self.editingNewTask:
            self._selected_task_id = str(self._all_tasks[0].get("id", ""))
        current_draft_id = str(self._draft.get("id", "")).strip()
        if self._selected_task_id and (
            not self._draft_dirty or current_draft_id != self._selected_task_id
        ):
            task = self._selected_task()
            if task is not None:
                self._draft = _draft_from_task(task)
                self._draft_dirty = False
        self._apply_projection()
        self.draftChanged.emit()
        self._set_error("")

    def _on_save_done(self, future: Any) -> None:
        if future.cancelled():
            self._set_busy(False)
            return
        exc = future.exception()
        if exc is not None:
            self._saveResult.emit(False, str(exc), "")
            return
        task_id, message = future.result()
        self._saveResult.emit(True, message, task_id)

    def _handle_save_result(self, ok: bool, error: str, task_id: str) -> None:
        self._set_busy(False)
        if not ok:
            self._set_error(error)
            self._set_notice(error, False)
            return
        self._selected_task_id = task_id
        self._draft_dirty = False
        self.selectedTaskChanged.emit()
        self.draftChanged.emit()
        self._set_error("")
        self._set_notice(error, True)
        self.refresh()

    def _on_delete_done(self, future: Any) -> None:
        if future.cancelled():
            self._set_busy(False)
            return
        exc = future.exception()
        if exc is not None:
            self._deleteResult.emit(False, str(exc), "")
            return
        task_id, removed = future.result()
        if not removed:
            self._deleteResult.emit(False, _tr(self._lang, "任务不存在", "Task not found"), task_id)
            return
        self._deleteResult.emit(True, _tr(self._lang, "任务已删除", "Task deleted"), task_id)

    def _handle_delete_result(self, ok: bool, error: str, task_id: str) -> None:
        self._set_busy(False)
        if not ok:
            self._set_error(error)
            self._set_notice(error, False)
            return
        if self._selected_task_id == task_id:
            self._selected_task_id = ""
            self._draft = _empty_draft()
            self._draft_dirty = False
            self.selectedTaskChanged.emit()
            self.draftChanged.emit()
        self._set_error("")
        self._set_notice(error, True)
        self.refresh()

    def _on_toggle_done(self, future: Any) -> None:
        if future.cancelled():
            self._set_busy(False)
            return
        exc = future.exception()
        if exc is not None:
            self._toggleResult.emit(False, str(exc), "")
            return
        task_id, ok = future.result()
        if not ok:
            self._toggleResult.emit(False, _tr(self._lang, "任务不存在", "Task not found"), task_id)
            return
        self._toggleResult.emit(True, _tr(self._lang, "任务已更新", "Task updated"), task_id)

    def _handle_toggle_result(self, ok: bool, error: str, _task_id: str) -> None:
        self._set_busy(False)
        if not ok:
            self._set_error(error)
            self._set_notice(error, False)
            return
        self._set_error("")
        self._set_notice(error, True)
        self.refresh()

    def _on_run_done(self, future: Any) -> None:
        if future.cancelled():
            self._set_busy(False)
            return
        exc = future.exception()
        if exc is not None:
            self._runResult.emit(False, str(exc))
            return
        ok = bool(future.result())
        self._runResult.emit(
            ok,
            _tr(self._lang, "任务已开始执行", "Task started")
            if ok
            else _tr(self._lang, "任务未能启动", "Task could not be started"),
        )

    def _handle_run_result(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        if not ok:
            self._set_error(message)
            self._set_notice(message, False)
            return
        self._set_error("")
        self._set_notice(message, True)
        self.refresh()
