from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore")

from app.backend.profile import ProfileService
from bao.profile import create_profile, rename_profile


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_profile_service_keeps_registry_projection_consistent(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "instructions"),
        ("PERSONA.md", "persona"),
        ("HEARTBEAT.md", "heartbeat"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")

    service = ProfileService()
    service.refreshFromWorkspace(str(shared_workspace))

    assert service.sharedWorkspacePath == str(shared_workspace)
    assert service.activeProfile["id"] == service.activeProfileId
    assert service.activeProfileContext["profileId"] == service.activeProfileId
    assert any(item["isActive"] for item in service.profiles)

    service.createProfile("Work")

    active_profile = service.activeProfile
    work_id = str(active_profile["id"])
    assert work_id.startswith("prof-")
    assert active_profile["displayName"] == "Work"
    assert active_profile["storageKey"] == "work"
    assert service.activeProfileContext["profileId"] == work_id
    assert service.activeProfileContext["storageKey"] == "work"
    assert any(item["id"] == work_id and item["isActive"] for item in service.profiles)

    service.deleteProfile(work_id)

    assert service.activeProfileId == "default"
    assert service.activeProfileContext["profileId"] == "default"
    assert all(item["id"] != work_id for item in service.profiles)


def test_profile_service_rename_updates_active_projection(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "instructions"),
        ("PERSONA.md", "persona"),
        ("HEARTBEAT.md", "heartbeat"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")

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
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "instructions"),
        ("PERSONA.md", "persona"),
        ("HEARTBEAT.md", "heartbeat"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")

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
    shared_workspace.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("INSTRUCTIONS.md", "instructions"),
        ("PERSONA.md", "persona"),
        ("HEARTBEAT.md", "heartbeat"),
    ):
        (shared_workspace / filename).write_text(content, encoding="utf-8")

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
