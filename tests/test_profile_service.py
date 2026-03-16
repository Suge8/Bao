# ruff: noqa: E402

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication
QEventLoop = QtCore.QEventLoop
QTimer = QtCore.QTimer

from app.backend.asyncio_runner import AsyncioRunner
from app.backend.profile import ProfileService
from bao.profile import create_profile, rename_profile


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
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


def _spin(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _write_workspace(shared_workspace: Path) -> None:
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "instructions"),
        ("PERSONA.md", "persona"),
        ("HEARTBEAT.md", "heartbeat"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")


def test_profile_service_keeps_registry_projection_consistent(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    service = ProfileService()
    service.refreshFromWorkspace(str(shared_workspace))

    assert service.sharedWorkspacePath == str(shared_workspace)
    assert service.activeProfile["id"] == service.activeProfileId
    assert service.activeProfileContext["profileId"] == service.activeProfileId
    assert any(item["isActive"] for item in service.profiles)

    service.createProfile("Work")

    active_profile = service.activeProfile
    work_id = str(active_profile["id"])
    registry_snapshot = service.registrySnapshot
    assert work_id.startswith("prof-")
    assert active_profile["displayName"] == "Work"
    assert active_profile["storageKey"] == "work"
    assert service.activeProfileContext["profileId"] == work_id
    assert service.activeProfileContext["storageKey"] == "work"
    assert registry_snapshot["activeProfileId"] == work_id
    assert registry_snapshot["defaultProfileId"] == "default"
    assert any(
        item["id"] == work_id and item["storage_key"] == "work"
        for item in registry_snapshot["profiles"]
    )
    assert any(item["id"] == work_id and item["isActive"] for item in service.profiles)

    service.deleteProfile(work_id)

    assert service.activeProfileId == "default"
    assert service.activeProfileContext["profileId"] == "default"
    assert service.registrySnapshot["activeProfileId"] == "default"
    assert all(item["id"] != work_id for item in service.profiles)


def test_profile_service_rename_updates_active_projection(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    service = ProfileService()
    service.refreshFromWorkspace(str(shared_workspace))
    service.createProfile("Work")
    work_id = str(service.activeProfile["id"])
    service.renameProfile(work_id, "Research")

    assert service.activeProfileId == work_id
    assert service.activeProfile["displayName"] == "Research"
    assert service.activeProfileContext["displayName"] == "Research"
    assert any(
        item["id"] == work_id and item["displayName"] == "Research" and item["isActive"]
        for item in service.profiles
    )


def test_profile_service_update_profile_moves_storage_projection(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    service = ProfileService()
    service.refreshFromWorkspace(str(shared_workspace))
    service.createProfile("Work")
    work_id = str(service.activeProfile["id"])
    service.updateProfile(work_id, "Research", "research")

    assert service.activeProfileId == work_id
    assert service.activeProfile["displayName"] == "Research"
    assert service.activeProfile["storageKey"] == "research"
    assert service.activeProfileContext["storageKey"] == "research"
    assert any(
        item["id"] == work_id
        and item["displayName"] == "Research"
        and item["storageKey"] == "research"
        and item["isActive"]
        for item in service.profiles
    )


def test_profile_service_inactive_rename_does_not_emit_active_profile_changed(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    service = ProfileService()
    service.refreshFromWorkspace(str(shared_workspace))
    registry, _ = create_profile("Work", shared_workspace=shared_workspace, activate=False)
    work_id = str(registry.profiles[-1].id)
    rename_profile(work_id, "Research", shared_workspace=shared_workspace)

    profile_changes: list[int] = []
    active_changes: list[int] = []
    _ = service.profilesChanged.connect(lambda: profile_changes.append(1))
    _ = service.activeProfileChanged.connect(lambda: active_changes.append(1))

    service.refreshFromWorkspace(str(shared_workspace))

    assert len(profile_changes) == 1
    assert active_changes == []


def test_profile_service_refresh_from_workspace_is_async_with_runner(
    qt_app: QCoreApplication,
    fake_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = qt_app
    import app.backend.profile as profile_module

    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    real_loader = profile_module.load_active_profile_snapshot
    release_loader = threading.Event()
    loader_started = threading.Event()
    loader_threads: list[int] = []

    def blocked_loader(*, shared_workspace: Path):
        loader_threads.append(threading.get_ident())
        loader_started.set()
        assert release_loader.wait(1.0)
        return real_loader(shared_workspace=shared_workspace)

    monkeypatch.setattr(profile_module, "load_active_profile_snapshot", blocked_loader)
    runner = AsyncioRunner()
    runner.start()
    try:
        service = ProfileService(runner)
        active_changes: list[int] = []
        _ = service.activeProfileChanged.connect(lambda: active_changes.append(1))

        started_at = time.perf_counter()
        service.refreshFromWorkspace(str(shared_workspace))
        elapsed = time.perf_counter() - started_at

        assert elapsed < 0.2
        assert loader_started.wait(0.5)
        assert service.activeProfileId == ""
        assert active_changes == []

        release_loader.set()
        _wait_until(lambda: service.activeProfileId == "default")

        assert service.sharedWorkspacePath == str(shared_workspace)
        assert active_changes == [1]
        assert loader_threads and loader_threads[0] != threading.get_ident()
    finally:
        runner.shutdown()


def test_profile_service_sync_action_invalidates_stale_async_refresh(
    qt_app: QCoreApplication,
    fake_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = qt_app
    import app.backend.profile as profile_module

    shared_workspace = fake_home / ".bao" / "workspace"
    _write_workspace(shared_workspace)

    stale_snapshot = profile_module.load_active_profile_snapshot(shared_workspace=shared_workspace)
    release_loader = threading.Event()
    loader_started = threading.Event()
    loader_finished = threading.Event()

    def blocked_loader(*, shared_workspace: Path):
        loader_started.set()
        assert release_loader.wait(1.0)
        loader_finished.set()
        return stale_snapshot

    monkeypatch.setattr(profile_module, "load_active_profile_snapshot", blocked_loader)
    runner = AsyncioRunner()
    runner.start()
    try:
        service = ProfileService(runner)
        service.refreshFromWorkspace(str(shared_workspace))

        assert loader_started.wait(0.5)
        service.createProfile("Work")

        work_id = str(service.activeProfile["id"])
        assert work_id.startswith("prof-")
        assert service.activeProfile["displayName"] == "Work"

        release_loader.set()
        assert loader_finished.wait(0.5)
        _spin(100)

        assert service.activeProfileId == work_id
        assert service.activeProfile["displayName"] == "Work"
    finally:
        runner.shutdown()
