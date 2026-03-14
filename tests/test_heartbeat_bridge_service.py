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


class _FakeResponse:
    has_tool_calls = False
    tool_calls: list[object] = []


class _FakeProvider:
    async def chat(self, *args, **kwargs):
        return _FakeResponse()


class _FakeSessionService:
    def __init__(self) -> None:
        self.selected: list[str] = []

    def select_session(self, key: str) -> None:
        self.selected.append(key)

    def __getattr__(self, name: str):
        if name == "selectSession":
            return self.select_session
        raise AttributeError(name)


def test_heartbeat_bridge_reads_current_profile_file_when_live_is_stale(tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.heartbeat import HeartbeatBridgeService
    from bao.heartbeat.service import HeartbeatService

    runner = AsyncioRunner()
    runner.start()
    try:
        stale_prompt = tmp_path / "default" / "prompt"
        stale_prompt.mkdir(parents=True, exist_ok=True)
        (stale_prompt / "HEARTBEAT.md").write_text("default heartbeat", encoding="utf-8")

        current_prompt = tmp_path / "work" / "prompt"
        current_prompt.mkdir(parents=True, exist_ok=True)
        current_file = current_prompt / "HEARTBEAT.md"
        current_file.write_text(
            "# Work checks\n\n<!-- internal -->\n- review inbox\n1. triage follow-ups\n",
            encoding="utf-8",
        )

        service = HeartbeatBridgeService(runner)
        stale_live = HeartbeatService(stale_prompt, _FakeProvider(), "test")
        service.setLiveHeartbeatService(stale_live)
        service.setLocalHeartbeatFilePath(str(current_file))

        _wait_until(lambda: service.heartbeatPreview == "review inbox triage follow-ups")

        assert service.heartbeatFileExists is True
        assert service.heartbeatPreview == "review inbox triage follow-ups"
        assert service.canRunNow is False
        assert service.runNowBlockedReason == "Switching to the current space. Try again in a moment"
    finally:
        runner.shutdown(grace_s=1.0)


def test_heartbeat_bridge_runs_current_profile_live_service(tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.heartbeat import HeartbeatBridgeService
    from bao.heartbeat.service import HeartbeatService

    runner = AsyncioRunner()
    runner.start()
    try:
        prompt_root = tmp_path / "work" / "prompt"
        prompt_root.mkdir(parents=True, exist_ok=True)
        heartbeat_file = prompt_root / "HEARTBEAT.md"
        heartbeat_file.write_text("check inbox", encoding="utf-8")

        service = HeartbeatBridgeService(runner)
        session_service = _FakeSessionService()
        live = HeartbeatService(prompt_root, _FakeProvider(), "test")
        service.setSessionService(session_service)
        service.setLocalHeartbeatFilePath(str(heartbeat_file))
        service.setLiveHeartbeatService(live)
        service.setGatewayRunning(True)
        _wait_until(lambda: service.canRunNow is True)

        service.runNow()
        _wait_until(lambda: service.noticeText == "No new tasks found")

        assert service.noticeSuccess is True
        assert service.lastCheckedText != ""

        service.openHeartbeatSession()
        assert session_service.selected == ["heartbeat"]
    finally:
        runner.shutdown(grace_s=1.0)


def test_heartbeat_bridge_blocks_run_without_heartbeat_file(tmp_path: Path, qt_app) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.heartbeat import HeartbeatBridgeService
    from bao.heartbeat.service import HeartbeatService

    runner = AsyncioRunner()
    runner.start()
    try:
        prompt_root = tmp_path / "work" / "prompt"
        prompt_root.mkdir(parents=True, exist_ok=True)
        heartbeat_file = prompt_root / "HEARTBEAT.md"

        service = HeartbeatBridgeService(runner)
        live = HeartbeatService(prompt_root, _FakeProvider(), "test")
        service.setLocalHeartbeatFilePath(str(heartbeat_file))
        service.setLiveHeartbeatService(live)
        service.setGatewayRunning(True)
        _wait_until(lambda: service.heartbeatFileExists is False)

        assert service.canRunNow is False
        assert service.runNowBlockedReason == "Set up automatic check instructions before running this check"
    finally:
        runner.shutdown(grace_s=1.0)


def test_heartbeat_bridge_opens_current_profile_file_and_creates_template(
    tmp_path: Path, qt_app, monkeypatch
) -> None:
    _ = qt_app
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.heartbeat import HeartbeatBridgeService

    opened_urls: list[str] = []

    def _fake_open_url(url) -> bool:
        opened_urls.append(url.toLocalFile())
        return True

    monkeypatch.setattr("app.backend.heartbeat.QDesktopServices.openUrl", _fake_open_url)

    runner = AsyncioRunner()
    runner.start()
    try:
        prompt_root = tmp_path / "work" / "prompt"
        prompt_root.mkdir(parents=True, exist_ok=True)
        (prompt_root / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")
        heartbeat_file = prompt_root / "HEARTBEAT.md"

        service = HeartbeatBridgeService(runner)
        service.setLocalHeartbeatFilePath(str(heartbeat_file))
        service.openHeartbeatFile()

        _wait_until(lambda: heartbeat_file.exists())

        assert opened_urls == [str(heartbeat_file)]
        assert heartbeat_file.read_text(encoding="utf-8").strip() != ""
    finally:
        runner.shutdown(grace_s=1.0)
