from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.gui]

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer
QGuiApplication = QtGui.QGuiApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _wait_until(predicate, timeout_ms: int = 2000) -> None:
    loop = QEventLoop()

    def check() -> None:
        if predicate():
            loop.quit()

    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(check)
    timer.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    check()
    loop.exec()
    timer.stop()
    if not predicate():
        raise AssertionError("Timed out waiting for condition")


class _FakeSessionService:
    def __init__(self) -> None:
        self.selected: list[str] = []

    def select_session(self, key: str) -> None:
        self.selected.append(key)

    def __getattr__(self, name: str):
        if name == "selectSession":
            return self.select_session
        raise AttributeError(name)


def test_cron_bridge_refreshes_and_selects_first_job(monkeypatch, tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        service._local_cron.add_job(
            name="Morning Briefing",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="Send summary",
        )

        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)

        selected_task = service.property("selectedTask")
        draft = service.property("draft")
        tasks_model = service.property("tasksModel")

        assert service.selectedTaskId
        assert isinstance(selected_task, dict)
        assert isinstance(draft, dict)
        assert selected_task["name"] == "Morning Briefing"
        assert draft["name"] == "Morning Briefing"
        assert tasks_model.rowCount() == 1
    finally:
        runner.shutdown(grace_s=1.0)


def test_cron_bridge_can_create_and_update_job(monkeypatch, tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        service.newDraft()
        service.updateDraftField("name", "Nightly Review")
        service.updateDraftField("schedule_kind", "cron")
        service.updateDraftField("cron_expr", "0 21 * * *")
        service.updateDraftField("timezone", "Australia/Sydney")
        service.updateDraftField("message", "Review the project status")
        service.saveDraft()
        _wait_until(lambda: service.totalTaskCount == 1 and not service.busy)

        assert service.noticeText == "Task created"
        selected = service.property("selectedTask")
        assert isinstance(selected, dict)
        assert selected["name"] == "Nightly Review"
        assert selected["schedule_kind"] == "cron"

        service.updateDraftField("name", "Nightly Digest")
        service.saveDraft()
        _wait_until(
            lambda: (
                isinstance(service.property("selectedTask"), dict)
                and service.property("selectedTask").get("name") == "Nightly Digest"
                and not service.busy
            )
        )

        updated_task = service.property("selectedTask")
        assert isinstance(updated_task, dict)
        assert updated_task["name"] == "Nightly Digest"
        assert service.noticeText == "Task updated"
    finally:
        runner.shutdown(grace_s=1.0)


def test_cron_bridge_opens_selected_session(monkeypatch, tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        fake_session_service = _FakeSessionService()
        service.setSessionService(fake_session_service)
        job = service._local_cron.add_job(
            name="Ping",
            schedule=CronSchedule(kind="every", every_ms=120_000),
            message="Ping me",
        )
        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)

        service.selectTask(job.id)
        service.openSelectedSession()

        assert fake_session_service.selected == [f"cron:{job.id}"]
    finally:
        runner.shutdown(grace_s=1.0)


def test_cron_bridge_localizes_projection(monkeypatch, tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        service.setLanguage("zh")
        service._local_cron.add_job(
            name="中文任务",
            schedule=CronSchedule(kind="every", every_ms=180 * 60_000),
            message="发送中文摘要",
        )

        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)

        task = service.property("selectedTask")
        assert isinstance(task, dict)
        assert task["status_label"] == "已调度"
        assert "每 3 小时" in task["schedule_summary"]
        assert "从未执行" in task["last_result_text"]
    finally:
        runner.shutdown(grace_s=1.0)


def test_new_draft_clears_selection(monkeypatch, tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import _DRAFT_PREVIEW_ID, CronBridgeService
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        job = service._local_cron.add_job(
            name="Existing Task",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="Run existing task",
        )

        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)
        service.selectTask(job.id)

        assert service.selectedTaskId == job.id
        service.newDraft()

        assert service.selectedTaskId == ""
        assert service.hasSelection is False
        assert service.editingNewTask is True
        assert service.activeListItemId == _DRAFT_PREVIEW_ID
        assert service.totalTaskCount == 2
        assert service.visibleTaskCount == 2
        model = service.property("tasksModel")
        assert model.rowCount() == 2
        draft = service.property("draft")
        assert isinstance(draft, dict)
        assert draft.get("id") == ""
    finally:
        runner.shutdown(grace_s=1.0)


def test_selecting_existing_task_restores_saved_fields_after_new_draft(
    monkeypatch, tmp_path: Path, qt_app
) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        job = service._local_cron.add_job(
            name="Existing Task",
            schedule=CronSchedule(kind="every", every_ms=180 * 60_000),
            message="Run the saved task",
        )

        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)
        service.newDraft()
        _wait_until(lambda: service.visibleTaskCount == 2)

        service.selectTask(job.id)
        _wait_until(
            lambda: (
                service.selectedTaskId == job.id
                and isinstance(service.property("draft"), dict)
                and service.property("draft").get("name") == "Existing Task"
            )
        )

        draft = service.property("draft")
        assert isinstance(draft, dict)
        assert draft["name"] == "Existing Task"
        assert draft["message"] == "Run the saved task"
        assert service.visibleTaskCount == 1
    finally:
        runner.shutdown(grace_s=1.0)


def test_reselecting_same_task_repairs_stale_empty_draft(
    monkeypatch, tmp_path: Path, qt_app
) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.cron import CronBridgeService, _empty_draft
    from bao.cron.types import CronSchedule

    monkeypatch.setattr("app.backend.cron.get_data_dir", lambda: tmp_path)

    runner = AsyncioRunner()
    runner.start()
    try:
        service = CronBridgeService(runner)
        job = service._local_cron.add_job(
            name="Existing Task",
            schedule=CronSchedule(kind="every", every_ms=180 * 60_000),
            message="Run the saved task",
        )

        service.refresh()
        _wait_until(lambda: service.totalTaskCount == 1)
        service.selectTask(job.id)

        service._draft = _empty_draft()
        service._draft_dirty = True

        service.selectTask(job.id)

        draft = service.property("draft")
        assert isinstance(draft, dict)
        assert draft["id"] == job.id
        assert draft["name"] == "Existing Task"
        assert draft["message"] == "Run the saved task"
        assert service.editingNewTask is False
    finally:
        runner.shutdown(grace_s=1.0)
