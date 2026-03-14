# ruff: noqa: E402, N802, N815

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.gui]

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer
QObject = QtCore.QObject
Signal = QtCore.Signal
QGuiApplication = QtGui.QGuiApplication

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.profile import ProfileService
from app.backend.profile_supervisor import _SNAPSHOT_FILENAME, ProfileWorkSupervisorService
from bao.profile import profile_context, profile_context_from_mapping


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _wait_until(predicate, timeout_ms: int = 4000) -> None:
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


class _SessionModel:
    def __init__(self, sessions: list[dict[str, object]]) -> None:
        self._sessions = [dict(item) for item in sessions]


class _DummySessionService(QObject):
    sessionsChanged = Signal()
    sessionManagerReady = Signal(object)

    def __init__(self, sessions: list[dict[str, object]]) -> None:
        super().__init__()
        self._model = _SessionModel(sessions)
        self.selected: list[str] = []

    def selectSession(self, key: str) -> None:
        self.selected.append(key)

    def supervisorSessionsSnapshot(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._model._sessions]


class _DummyChatService(QObject):
    stateChanged = Signal(str)
    errorChanged = Signal(str)
    gatewayChannelsChanged = Signal()
    gatewayDetailChanged = Signal()
    startupActivityChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.state = "running"
        self.gatewayState = "running"
        self.gatewayDetail = ""
        self.lastError = ""
        self.gatewayDetailIsError = False
        self.gatewayChannels = ["desktop", "telegram"]
        self.startupActivity: dict[str, object] = {}
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> None:
        self.start_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def supervisorGatewaySnapshot(self) -> dict[str, object]:
        return {
            "state": self.gatewayState,
            "detail": self.gatewayDetail,
            "error": self.lastError,
            "detail_is_error": self.gatewayDetailIsError,
            "channels": list(self.gatewayChannels),
            "startup_activity": dict(self.startupActivity),
        }


class _DummyCronService(QObject):
    tasksChanged = Signal()
    profileChanged = Signal()

    def __init__(self, tasks: list[dict[str, object]]) -> None:
        super().__init__()
        self._all_tasks = [dict(item) for item in tasks]
        self._selected_task: dict[str, object] = {}
        self.selected: list[str] = []
        self.toggle_calls: list[bool] = []

    @property
    def selectedTask(self) -> dict[str, object]:
        return dict(self._selected_task)

    def selectTask(self, task_id: str) -> None:
        self.selected.append(task_id)
        self._selected_task = next(
            (dict(item) for item in self._all_tasks if str(item.get("id", "")) == task_id),
            {},
        )

    def toggleEnabled(self, enabled: bool) -> None:
        self.toggle_calls.append(bool(enabled))

    def supervisorTasksSnapshot(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._all_tasks]


class _DummyLiveHeartbeat:
    def __init__(self, running: bool) -> None:
        self._running = running

    def status(self) -> dict[str, object]:
        return {"running": self._running}


class _DummyHeartbeatService(QObject):
    stateChanged = Signal()
    profileChanged = Signal()

    def __init__(self, heartbeat_file: Path, *, running: bool = True) -> None:
        super().__init__()
        self.enabled = True
        self.heartbeatFilePath = str(heartbeat_file)
        self.heartbeatFileExists = heartbeat_file.exists()
        self.lastDecisionLabel = ""
        self.lastError = ""
        self._snapshot = {
            "last_checked_at_ms": 1_710_000_000_000,
            "last_run_at_ms": 1_710_000_060_000,
        }
        self._live = _DummyLiveHeartbeat(running)
        self.run_now_calls = 0

    def _effective_live(self) -> _DummyLiveHeartbeat:
        return self._live

    def runNow(self) -> None:
        self.run_now_calls += 1

    def supervisorSnapshot(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "heartbeat_file": self.heartbeatFilePath,
            "heartbeat_file_exists": self.heartbeatFileExists,
            "last_checked_at_ms": self._snapshot.get("last_checked_at_ms"),
            "last_run_at_ms": self._snapshot.get("last_run_at_ms"),
            "last_decision": self.lastDecisionLabel,
            "last_error": self.lastError,
            "running": self._live.status().get("running", False),
        }


def _write_workspace(shared_workspace: Path) -> None:
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "# Instructions\n"),
        ("PERSONA.md", "# Persona\n"),
        ("HEARTBEAT.md", "- review inbox\n"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")


def _session_item(
    *,
    key: str,
    title: str,
    updated_at: str,
    channel: str,
    visual_channel: str,
    is_child_session: bool,
    parent_session_key: str = "",
) -> dict[str, object]:
    return {
        "key": key,
        "title": title,
        "updated_at": updated_at,
        "updated_label": "刚刚",
        "channel": channel,
        "visual_channel": visual_channel,
        "child_status": "running" if is_child_session else "",
        "is_running": True,
        "is_child_session": is_child_session,
        "parent_session_key": parent_session_key,
    }


def _cron_item(task_id: str, *, title: str = "Daily Review") -> dict[str, object]:
    return {
        "id": task_id,
        "name": title,
        "enabled": True,
        "schedule_summary": "每 30 分钟",
        "status_key": "scheduled",
        "status_label": "已调度",
        "session_key": f"cron:{task_id}",
        "next_run_text": "2026-03-14 12:00",
        "last_result_text": "成功 · 2026-03-14 11:30",
        "updated_at_ms": 1_710_000_000_000,
        "last_error": "",
    }


def _write_work_snapshot(
    profile_context,
    *,
    session_key: str,
    snapshot_profile_id: str | None = None,
) -> None:
    profile_id = str(snapshot_profile_id or profile_context.profile_id)
    avatar_source = "../resources/profile-avatars/mochi.svg"
    session_item = {
        "id": f"{profile_id}:session_reply:{session_key}",
        "profileId": profile_id,
        "kind": "session_reply",
        "title": "Work Ops",
        "summary": "回复中",
        "sessionKey": session_key,
        "parentSessionKey": "",
        "visualChannel": "telegram",
        "accentKey": "telegram",
        "glyphSource": "../resources/icons/channel-telegram.svg",
        "statusKey": "running",
        "statusLabel": "运行中",
        "updatedAt": "2026-03-14T12:01:00+00:00",
        "updatedLabel": "刚刚",
        "relativeLabel": "刚刚",
        "isLive": False,
        "personaVariant": "primary",
        "avatarSource": avatar_source,
        "routeKind": "session",
        "routeValue": session_key,
        "canOpen": True,
        "canToggleCron": False,
        "canRunHeartbeat": False,
        "isRunning": True,
    }
    automation_item = {
        "id": f"{profile_id}:cron:daily-review",
        "profileId": profile_id,
        "kind": "cron_job",
        "title": "Daily Review",
        "summary": "每 30 分钟",
        "sessionKey": "cron:daily-review",
        "visualChannel": "cron",
        "accentKey": "cron",
        "glyphSource": "../resources/icons/sidebar-cron.svg",
        "statusKey": "scheduled",
        "statusLabel": "已调度",
        "updatedAt": "2026-03-14T12:01:00+00:00",
        "updatedLabel": "2 小时后",
        "relativeLabel": "2 小时后",
        "isLive": False,
        "personaVariant": "automation",
        "avatarSource": avatar_source,
        "routeKind": "cron",
        "routeValue": "daily-review",
        "canOpen": True,
        "canToggleCron": True,
        "canRunHeartbeat": False,
        "isRunning": False,
    }
    payload = {
        "schema_version": 1,
        "profile_id": profile_id,
        "display_name": "Work",
        "avatar_key": "mochi",
        "updated_at": "2026-03-14T12:02:00+00:00",
        "gateway": {"state": "running", "detail": "", "channels": ["telegram"], "is_live": False},
        "inventory": {
            "totalSessionCount": 1,
            "totalChildSessionCount": 0,
            "channelKeys": ["telegram"],
        },
        "workers": [
            {
                "workerId": f"{profile_id}:session",
                "profileId": profile_id,
                "avatarSource": avatar_source,
                "title": "Work Ops",
                "variant": "primary",
                "accentKey": "telegram",
                "glyphSource": "../resources/icons/channel-telegram.svg",
                "statusKey": "running",
                "statusLabel": "运行中",
                "routeKind": "session",
                "routeValue": session_key,
            }
        ],
        "working": [session_item],
        "automation": [automation_item],
        "attention": [],
    }
    snapshot_path = profile_context.state_root / _SNAPSHOT_FILENAME
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _build_supervisor(tmp_path: Path) -> tuple[
    AsyncioRunner,
    ProfileWorkSupervisorService,
    ProfileService,
    _DummySessionService,
    _DummyChatService,
    _DummyCronService,
    _DummyHeartbeatService,
    str,
]:
    shared_workspace = tmp_path / "workspace"
    _write_workspace(shared_workspace)

    profile_service = ProfileService()
    profile_service.refreshFromWorkspace(str(shared_workspace))
    profile_service.createProfile("Work")
    work_context = profile_context_from_mapping(profile_service.activeProfileContext)
    assert work_context is not None
    work_id = str(work_context.profile_id)
    _write_work_snapshot(work_context, session_key="telegram:work-room")
    profile_service.activateProfile("default")
    active_context = profile_context_from_mapping(profile_service.activeProfileContext)
    assert active_context is not None

    sessions = [
        _session_item(
            key="desktop:local::main",
            title="Main Thread",
            updated_at="2026-03-14T12:04:00+00:00",
            channel="desktop",
            visual_channel="desktop",
            is_child_session=False,
        ),
        _session_item(
            key="subagent:child",
            title="Code Worker",
            updated_at="2026-03-14T12:05:00+00:00",
            channel="desktop",
            visual_channel="desktop",
            is_child_session=True,
            parent_session_key="desktop:local::main",
        ),
    ]
    session_service = _DummySessionService(sessions)
    chat_service = _DummyChatService()
    cron_service = _DummyCronService([_cron_item("daily-review")])
    heartbeat_service = _DummyHeartbeatService(active_context.heartbeat_file, running=True)
    runner = AsyncioRunner()
    runner.start()
    supervisor = ProfileWorkSupervisorService(
        runner,
        profile_service=profile_service,
        session_service=session_service,
        chat_service=chat_service,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
    )
    return (
        runner,
        supervisor,
        profile_service,
        session_service,
        chat_service,
        cron_service,
        heartbeat_service,
        work_id,
    )


def test_supervisor_projects_live_and_snapshot_profiles(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        _chat_service,
        _cron_service,
        _heartbeat_service,
        work_id,
    ) = _build_supervisor(tmp_path)
    try:
        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)

        assert supervisor.overview["workingCount"] == 2
        assert supervisor.overview["automationCount"] == 3
        assert supervisor.selectedProfile == {}
        assert all(item["profileId"] == "default" for item in supervisor.workingItems)
        default_profile = next(item for item in supervisor.profiles if item["id"] == "default")
        work_profile = next(item for item in supervisor.profiles if item["id"] == work_id)
        assert default_profile["totalSessionCount"] == 1
        assert default_profile["totalChildSessionCount"] == 1
        assert default_profile["channelKeys"] == ["desktop", "telegram"]
        assert work_profile["totalSessionCount"] == 1
        assert work_profile["channelKeys"] == ["telegram"]
        assert work_profile["workingCount"] == 0
        assert any(item["id"] == work_id and item["isLive"] is False for item in supervisor.profiles)
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_queues_cross_profile_session_open(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        profile_service,
        session_service,
        _chat_service,
        _cron_service,
        _heartbeat_service,
        work_id,
    ) = _build_supervisor(tmp_path)
    try:
        routes: list[str] = []
        supervisor.profileNavigationRequested.connect(routes.append)

        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)
        supervisor.selectProfile(work_id)
        _wait_until(lambda: supervisor.selectedProfile.get("id") == work_id)

        target = next(
            item
            for item in supervisor.automationItems
            if item["profileId"] == work_id and item["routeKind"] == "cron"
        )
        supervisor.selectItem(str(target["id"]))
        supervisor.openSelectedTarget()

        assert profile_service.activeProfileId == work_id
        assert session_service.selected == []

        session_service.sessionManagerReady.emit(object())

        assert routes == ["cron"]
        assert _cron_service.selected == [str(target["routeValue"])]
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_normalizes_legacy_snapshot_profile_ids(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        _chat_service,
        _cron_service,
        _heartbeat_service,
        work_id,
    ) = _build_supervisor(tmp_path)
    try:
        shared_workspace = tmp_path / "workspace"
        work_context = profile_context(work_id, shared_workspace=shared_workspace)
        snapshot_path = work_context.state_root / _SNAPSHOT_FILENAME
        _write_work_snapshot(
            work_context,
            session_key="telegram:legacy-room",
            snapshot_profile_id="work",
        )
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["attention"] = [
            {
                "id": "work:gateway:issue",
                "profileId": "work",
                "kind": "issue",
                "title": "网关状态",
                "summary": "请查看网关状态",
                "statusKey": "error",
                "statusLabel": "待处理",
                "visualChannel": "system",
                "accentKey": "system",
                "glyphSource": "../resources/icons/sidebar-pulse.svg",
                "updatedAt": payload["updated_at"],
                "updatedLabel": "刚刚",
                "relativeLabel": "刚刚",
                "isLive": False,
                "personaVariant": "automation",
                "avatarSource": "../resources/profile-avatars/mochi.svg",
                "routeKind": "profile",
                "routeValue": "work",
                "canOpen": True,
                "canToggleCron": False,
                "canRunHeartbeat": False,
            }
        ]
        snapshot_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)
        supervisor.selectProfile(work_id)
        _wait_until(lambda: supervisor.selectedProfile.get("id") == work_id)

        selected_profile = supervisor.selectedProfile
        assert all(item["profileId"] == work_id for item in supervisor.automationItems)
        assert all(item["id"].startswith(f"{work_id}:") for item in supervisor.automationItems)
        assert all(item["profileId"] == work_id for item in supervisor.attentionItems)
        assert any(item["routeValue"] == work_id for item in supervisor.attentionItems)
        assert all(worker["profileId"] == work_id for worker in selected_profile["workers"])
        assert all(worker["workerId"].startswith(f"{work_id}:") for worker in selected_profile["workers"])

        normalized = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert normalized["profile_id"] == work_id
        assert all(item["profileId"] == work_id for item in normalized["automation"])
        assert all(item["id"].startswith(f"{work_id}:") for item in normalized["automation"])
        assert all(item["profileId"] == work_id for item in normalized["attention"])
        assert normalized["attention"][0]["routeValue"] == work_id
        assert all(worker["profileId"] == work_id for worker in normalized["workers"])
        assert all(worker["workerId"].startswith(f"{work_id}:") for worker in normalized["workers"])
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_hides_live_work_when_gateway_is_not_running(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        chat_service,
        _cron_service,
        _heartbeat_service,
        _work_id,
    ) = _build_supervisor(tmp_path)
    try:
        chat_service.state = "stopped"
        chat_service.gatewayState = "idle"
        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)
        supervisor.selectProfile("default")
        _wait_until(lambda: supervisor.selectedProfile.get("id") == "default")

        assert supervisor.selectedProfile["isGatewayLive"] is False
        assert supervisor.selectedProfile["workingCount"] == 0
        assert supervisor.workingItems == []
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_formats_automation_time_as_relative_label(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        _chat_service,
        _cron_service,
        _heartbeat_service,
        _work_id,
    ) = _build_supervisor(tmp_path)
    try:
        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)
        cron_item = next(
            item
            for item in supervisor.automationItems
            if str(item.get("routeKind", "")) == "cron" and str(item.get("profileId", "")) == "default"
        )
        assert "2026" not in str(cron_item.get("updatedLabel", ""))
        assert str(cron_item.get("updatedLabel", "")).endswith(("前", "后")) or str(
            cron_item.get("updatedLabel", "")
        ) == "刚刚"
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_select_profile_emits_filtered_collections_immediately(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        _chat_service,
        _cron_service,
        _heartbeat_service,
        work_id,
    ) = _build_supervisor(tmp_path)
    try:
        working_events: list[int] = []
        automation_events: list[int] = []
        attention_events: list[int] = []
        supervisor.workingChanged.connect(lambda: working_events.append(len(supervisor.workingItems)))
        supervisor.automationChanged.connect(lambda: automation_events.append(len(supervisor.automationItems)))
        supervisor.attentionChanged.connect(lambda: attention_events.append(len(supervisor.attentionItems)))

        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)

        supervisor.selectProfile(work_id)

        assert supervisor.selectedProfile["id"] == work_id
        assert supervisor.workingItems == []
        assert all(item["profileId"] == work_id for item in supervisor.automationItems)
        assert working_events
        assert automation_events
        assert attention_events
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_does_not_project_gateway_summary_as_attention(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        chat_service,
        _cron_service,
        _heartbeat_service,
        _work_id,
    ) = _build_supervisor(tmp_path)
    try:
        chat_service.gatewayDetail = "✓ 网关已启动 — 通道: telegram"
        chat_service.lastError = ""
        chat_service.gatewayDetailIsError = False

        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)

        assert not any(
            str(item.get("id", "")).endswith(":gateway:issue")
            for item in supervisor.attentionItems
        )
    finally:
        runner.shutdown(grace_s=1.0)


def test_supervisor_projects_startup_greeting_into_working_and_completed(
    tmp_path: Path, qt_app, fake_home: Path
) -> None:
    _ = qt_app
    _ = fake_home
    (
        runner,
        supervisor,
        _profile_service,
        _session_service,
        chat_service,
        _cron_service,
        _heartbeat_service,
        _work_id,
    ) = _build_supervisor(tmp_path)
    try:
        chat_service.startupActivity = {
            "kind": "startup_greeting",
            "status": "running",
            "sessionKey": "desktop:local::main",
            "sessionKeys": ["desktop:local::main", "imessage:13800138000"],
            "channelKeys": ["desktop", "imessage"],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

        supervisor.refresh()
        _wait_until(lambda: supervisor.overview.get("profileCount") == 2)

        running_item = next(
            item
            for item in supervisor.workingItems
            if str(item.get("kind", "")) == "startup_greeting"
        )
        assert running_item["statusKey"] == "running"
        assert running_item["statusLabel"] == "发送中"
        assert running_item["channelKeys"] == ["imessage", "desktop"]
        assert running_item["accentKey"] == "imessage"

        chat_service.startupActivity = {
            "kind": "startup_greeting",
            "status": "completed",
            "sessionKey": "desktop:local::main",
            "sessionKeys": ["desktop:local::main", "imessage:13800138000"],
            "channelKeys": ["desktop", "imessage"],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        supervisor.refresh()
        _wait_until(
            lambda: any(
                str(item.get("kind", "")) == "startup_greeting"
                for item in supervisor.completedItems
            )
        )

        assert not any(
            str(item.get("kind", "")) == "startup_greeting"
            for item in supervisor.workingItems
        )
        completed_item = next(
            item
            for item in supervisor.completedItems
            if str(item.get("kind", "")) == "startup_greeting"
        )
        assert completed_item["statusKey"] == "completed"
        assert completed_item["statusLabel"] == "已完成"
        assert completed_item["channelKeys"] == ["imessage", "desktop"]
        assert completed_item["routeKind"] == "profile"
    finally:
        runner.shutdown(grace_s=1.0)
