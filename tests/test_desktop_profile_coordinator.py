# ruff: noqa: N802

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore")

from app.backend.profile_binding import (
    DesktopProfileCoordinator,
    DesktopProfileCoordinatorOptions,
)
from bao.profile import ProfileContext, profile_context_to_dict


def _context(name: str, root: Path) -> ProfileContext:
    return ProfileContext(
        profile_id=name,
        display_name=name.title(),
        storage_key=name,
        shared_workspace_path=root / "workspace",
        profile_root=root / "profiles" / name,
        prompt_root=root / "profiles" / name / "prompt",
        state_root=root / "profiles" / name / "state",
        cron_store_path=root / "profiles" / name / "cron" / "jobs.json",
        heartbeat_file=root / "profiles" / name / "prompt" / "HEARTBEAT.md",
    )


class _DummyConfigService:
    def __init__(self, workspace: str) -> None:
        self.workspace = workspace

    def get(self, key: str, default: object) -> object:
        if key == "agents.defaults.workspace":
            return self.workspace
        return default


class _DummyProfileService:
    def __init__(self, context: ProfileContext | None = None) -> None:
        self.activeProfileContext = profile_context_to_dict(context)
        self.refresh_calls: list[str] = []

    def refreshFromWorkspace(self, workspace_path: str) -> None:
        self.refresh_calls.append(workspace_path)


class _DummyChatService:
    def __init__(self, *, state: str = "stopped") -> None:
        self.state = state
        self.profile_contexts: list[object] = []
        self.stop_calls = 0
        self.start_calls = 0
        self.restart_calls = 0

    def setProfileContext(self, data: object) -> None:
        self.profile_contexts.append(data)

    def stop(self) -> None:
        self.stop_calls += 1
        self.state = "stopped"

    def start(self) -> None:
        self.start_calls += 1
        self.state = "running"

    def restart(self) -> None:
        self.restart_calls += 1


class _DummySessionService:
    def __init__(self) -> None:
        self.bootstraps: list[str] = []

    def bootstrapStorageRoot(self, root: str) -> None:
        self.bootstraps.append(root)


class _DummyMemoryService:
    def __init__(self) -> None:
        self.hints: list[str] = []
        self.bootstraps: list[str] = []

    def setStorageRootHint(self, root: str) -> None:
        self.hints.append(root)

    def bootstrapStorageRoot(self, root: str) -> None:
        self.bootstraps.append(root)


class _DummyCronService:
    def __init__(self) -> None:
        self.profile_info: list[tuple[str, str]] = []
        self.store_paths: list[str] = []

    def setProfileInfo(self, profile_id: str, profile_name: str) -> None:
        self.profile_info.append((profile_id, profile_name))

    def setLocalStorePath(self, path: str) -> None:
        self.store_paths.append(path)


class _DummyHeartbeatService:
    def __init__(self) -> None:
        self.profile_info: list[tuple[str, str]] = []
        self.file_paths: list[str] = []

    def setProfileInfo(self, profile_id: str, profile_name: str) -> None:
        self.profile_info.append((profile_id, profile_name))

    def setLocalHeartbeatFilePath(self, path: str) -> None:
        self.file_paths.append(path)


class _DummySkillsService:
    def __init__(self) -> None:
        self.workspace_paths: list[str] = []

    def setWorkspacePath(self, path: str) -> None:
        self.workspace_paths.append(path)


def _make_coordinator(
    tmp_path: Path,
    *,
    profile_context: ProfileContext | None = None,
    chat_state: str = "stopped",
    session_service: _DummySessionService | None = None,
    memory_service: _DummyMemoryService | None = None,
    cron_service: _DummyCronService | None = None,
    heartbeat_service: _DummyHeartbeatService | None = None,
    skills_service: _DummySkillsService | None = None,
) -> tuple[
    DesktopProfileCoordinator,
    _DummyProfileService,
    _DummyChatService,
    _DummySessionService,
    _DummyMemoryService,
    _DummyCronService,
    _DummyHeartbeatService,
    _DummySkillsService,
]:
    profile_service = _DummyProfileService(profile_context)
    chat_service = _DummyChatService(state=chat_state)
    resolved_session_service = session_service or _DummySessionService()
    resolved_memory_service = memory_service or _DummyMemoryService()
    resolved_cron_service = cron_service or _DummyCronService()
    resolved_heartbeat_service = heartbeat_service or _DummyHeartbeatService()
    resolved_skills_service = skills_service or _DummySkillsService()
    coordinator = DesktopProfileCoordinator(
        DesktopProfileCoordinatorOptions(
            config_service=_DummyConfigService(str(tmp_path / "workspace")),
            profile_service=profile_service,
            chat_service=chat_service,
            session_service=resolved_session_service,
            memory_service=resolved_memory_service,
            cron_service=resolved_cron_service,
            heartbeat_service=resolved_heartbeat_service,
            skills_service=resolved_skills_service,
        )
    )
    return (
        coordinator,
        profile_service,
        chat_service,
        resolved_session_service,
        resolved_memory_service,
        resolved_cron_service,
        resolved_heartbeat_service,
        resolved_skills_service,
    )


def test_refresh_from_config_updates_profile_and_skills_workspace(tmp_path: Path) -> None:
    coordinator, profile_service, _chat_service, _session_service, _memory_service, _cron_service, _heartbeat_service, skills_service = _make_coordinator(tmp_path)

    coordinator.refresh_from_config()

    expected = str((tmp_path / "workspace").expanduser())
    assert profile_service.refresh_calls == [expected]
    assert skills_service.workspace_paths == [expected]


def test_running_hub_switch_stops_once_and_restarts_after_ready(tmp_path: Path) -> None:
    work = _context("work", tmp_path)
    (
        coordinator,
        _profile_service,
        chat_service,
        session_service,
        memory_service,
        cron_service,
        heartbeat_service,
        _skills_service,
    ) = _make_coordinator(
        tmp_path,
        profile_context=work,
        chat_state="running",
    )

    coordinator.apply_active_profile()

    assert chat_service.stop_calls == 0
    assert chat_service.restart_calls == 0
    assert session_service.bootstraps == [str(work.state_root)]
    assert memory_service.hints == [str(work.state_root)]
    assert memory_service.bootstraps == []
    assert cron_service.store_paths == [str(work.cron_store_path)]
    assert heartbeat_service.file_paths == [str(work.heartbeat_file)]
    assert cron_service.profile_info == [(work.profile_id, work.display_name)]
    assert heartbeat_service.profile_info == [(work.profile_id, work.display_name)]


def test_same_profile_context_does_not_rebootstrap_or_restart(tmp_path: Path) -> None:
    work = _context("work", tmp_path)
    (
        coordinator,
        _profile_service,
        chat_service,
        session_service,
        memory_service,
        cron_service,
        heartbeat_service,
        _skills_service,
    ) = _make_coordinator(tmp_path, profile_context=work)

    coordinator.apply_active_profile()
    coordinator.apply_active_profile()

    assert chat_service.stop_calls == 0
    assert chat_service.start_calls == 0
    assert chat_service.restart_calls == 0
    assert session_service.bootstraps == [str(work.state_root)]
    assert memory_service.hints == [str(work.state_root)]
    assert memory_service.bootstraps == []
    assert cron_service.store_paths == [str(work.cron_store_path)]
    assert heartbeat_service.file_paths == [str(work.heartbeat_file)]


def test_profile_rename_does_not_restart_running_hub(tmp_path: Path) -> None:
    work = _context("work", tmp_path)
    renamed = ProfileContext(
        profile_id=work.profile_id,
        display_name="Research",
        storage_key=work.storage_key,
        shared_workspace_path=work.shared_workspace_path,
        profile_root=work.profile_root,
        prompt_root=work.prompt_root,
        state_root=work.state_root,
        cron_store_path=work.cron_store_path,
        heartbeat_file=work.heartbeat_file,
    )
    (
        coordinator,
        profile_service,
        chat_service,
        _session_service,
        _memory_service,
        _cron_service,
        _heartbeat_service,
        _skills_service,
    ) = _make_coordinator(
        tmp_path,
        profile_context=work,
    )

    coordinator.apply_active_profile()
    chat_service.state = "running"
    profile_service.activeProfileContext = profile_context_to_dict(renamed)
    coordinator.apply_active_profile()

    assert chat_service.stop_calls == 0
    assert chat_service.start_calls == 0
    assert chat_service.restart_calls == 0
