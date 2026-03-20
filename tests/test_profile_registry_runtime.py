# ruff: noqa: F403, F405
from __future__ import annotations

from tests._profile_registry_testkit import *


def test_set_active_profile_updates_registry(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    _, created = create_profile(
        "Lab",
        CreateProfileOptions(shared_workspace=shared_workspace, activate=False),
    )
    updated, context = set_active_profile(created.profile_id, shared_workspace=shared_workspace)

    assert updated.active_profile_id == created.profile_id
    assert context.profile_id == created.profile_id


def test_load_active_profile_snapshot_returns_registry_and_context(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    registry, context = load_active_profile_snapshot(shared_workspace=shared_workspace)

    assert registry.active_profile_id == "default"
    assert context.profile_id == "default"


def test_profile_context_mapping_round_trip(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    _, context = create_profile("Work", CreateProfileOptions(shared_workspace=shared_workspace))

    restored = profile_context_from_mapping(profile_context_to_dict(context))

    assert restored == context
