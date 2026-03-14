from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from bao.profile import (
    PROFILE_AVATAR_KEYS,
    create_profile,
    delete_profile,
    ensure_profile_registry,
    load_active_profile_snapshot,
    profile_context_from_mapping,
    profile_context_to_dict,
    profile_runtime_metadata,
    rename_profile,
    set_active_profile,
    update_profile,
)


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_profile_registry_migrates_legacy_workspace_data(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    (shared_workspace / "INSTRUCTIONS.md").write_text("hello", encoding="utf-8")
    (shared_workspace / "PERSONA.md").write_text("persona", encoding="utf-8")
    (shared_workspace / "HEARTBEAT.md").write_text("heartbeat", encoding="utf-8")
    legacy_db = shared_workspace / "lancedb"
    legacy_db.mkdir()
    (legacy_db / "marker.txt").write_text("db", encoding="utf-8")
    legacy_cron_dir = fake_home / ".bao" / "cron"
    legacy_cron_dir.mkdir(parents=True, exist_ok=True)
    (legacy_cron_dir / "jobs.json").write_text(json.dumps({"jobs": []}), encoding="utf-8")

    registry = ensure_profile_registry(shared_workspace)
    default_profile = fake_home / ".bao" / "profiles" / "default"

    assert registry.default_profile_id == "default"
    assert registry.active_profile_id == "default"
    assert registry.get("default").avatar_key in PROFILE_AVATAR_KEYS
    assert (fake_home / ".bao" / "profiles.json").exists()
    assert (default_profile / "prompt" / "INSTRUCTIONS.md").read_text(encoding="utf-8") == "hello"
    assert (default_profile / "prompt" / "PERSONA.md").read_text(encoding="utf-8") == "persona"
    assert (default_profile / "prompt" / "HEARTBEAT.md").read_text(encoding="utf-8") == "heartbeat"
    assert (default_profile / "state" / "lancedb" / "marker.txt").read_text(encoding="utf-8") == "db"
    assert (default_profile / "cron" / "jobs.json").exists()


def test_create_profile_clones_shared_prompt_defaults_without_persona(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    (shared_workspace / "INSTRUCTIONS.md").write_text("instructions", encoding="utf-8")
    (shared_workspace / "PERSONA.md").write_text("persona", encoding="utf-8")
    (shared_workspace / "HEARTBEAT.md").write_text("heartbeat", encoding="utf-8")

    ensure_profile_registry(shared_workspace)
    registry, context = create_profile("Work Mode", shared_workspace=shared_workspace)

    assert registry.active_profile_id == context.profile_id
    assert re.fullmatch(r"prof-[0-9a-f]{12}", context.profile_id)
    assert context.storage_key == "work-mode"
    assert registry.get(context.profile_id).avatar_key in PROFILE_AVATAR_KEYS
    assert (context.prompt_root / "INSTRUCTIONS.md").read_text(encoding="utf-8") == "instructions"
    assert (context.prompt_root / "HEARTBEAT.md").read_text(encoding="utf-8") == "heartbeat"
    assert not (context.prompt_root / "PERSONA.md").exists()


def test_profile_registry_repairs_invalid_registry_file(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    registry_path = fake_home / ".bao" / "profiles.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{invalid", encoding="utf-8")

    registry = ensure_profile_registry(shared_workspace)

    assert registry.default_profile_id == "default"
    assert json.loads(registry_path.read_text(encoding="utf-8"))["default_profile_id"] == "default"


def test_profile_registry_migrates_legacy_ids_and_backfills_storage_key(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    registry_path = fake_home / ".bao" / "profiles.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_profile_id": "default",
                "active_profile_id": "work",
                "profiles": [
                    {
                        "id": "default",
                        "display_name": "Default",
                        "avatar_key": "mochi",
                        "enabled": True,
                    },
                    {
                        "id": "work",
                        "display_name": "Work",
                        "avatar_key": "kiwi",
                        "enabled": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = ensure_profile_registry(shared_workspace)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))

    work_profile = next(profile for profile in registry.profiles if profile.display_name == "Work")
    assert registry.get("default").storage_key == "default"
    assert re.fullmatch(r"prof-[0-9a-f]{12}", work_profile.id)
    assert work_profile.storage_key == "work"
    assert registry.active_profile_id == work_profile.id
    assert payload["profiles"][0]["storage_key"] == "default"
    assert re.fullmatch(r"prof-[0-9a-f]{12}", payload["profiles"][1]["id"])
    assert payload["profiles"][1]["storage_key"] == "work"
    assert payload["active_profile_id"] == work_profile.id


def test_profile_registry_backfills_empty_default_state_from_workspace(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    (shared_workspace / "lancedb").mkdir(parents=True, exist_ok=True)
    (shared_workspace / "lancedb" / "marker.txt").write_text("workspace-db", encoding="utf-8")

    target_lancedb = fake_home / ".bao" / "profiles" / "default" / "state" / "lancedb"
    target_lancedb.mkdir(parents=True, exist_ok=True)
    (target_lancedb / "placeholder.txt").write_text("empty", encoding="utf-8")

    def fake_has_data(path: Path) -> bool:
        resolved = path.expanduser()
        if resolved == shared_workspace:
            return True
        if resolved == fake_home / ".bao":
            return False
        if resolved == fake_home / ".bao" / "profiles" / "default" / "state":
            return False
        return False

    with patch("bao.profile._state_has_meaningful_data", side_effect=fake_has_data):
        ensure_profile_registry(shared_workspace)

    assert (target_lancedb / "marker.txt").read_text(encoding="utf-8") == "workspace-db"
    assert not (target_lancedb / "placeholder.txt").exists()


def test_profile_registry_skips_default_state_scan_after_bootstrap(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)

    with patch(
        "bao.profile._state_has_meaningful_data",
        side_effect=AssertionError("steady-state startup should not rescan default state"),
    ):
        ensure_profile_registry(shared_workspace)


def test_profile_registry_migrates_default_state_from_explicit_data_dir(fake_home: Path) -> None:
    shared_workspace = fake_home / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    custom_data_dir = fake_home / "custom-bao"
    custom_lancedb = custom_data_dir / "lancedb"
    custom_lancedb.mkdir(parents=True, exist_ok=True)
    (custom_lancedb / "marker.txt").write_text("custom-db", encoding="utf-8")
    custom_cron_dir = custom_data_dir / "cron"
    custom_cron_dir.mkdir(parents=True, exist_ok=True)
    (custom_cron_dir / "jobs.json").write_text(json.dumps({"jobs": ["custom"]}), encoding="utf-8")

    global_lancedb = fake_home / ".bao" / "lancedb"
    global_lancedb.mkdir(parents=True, exist_ok=True)
    (global_lancedb / "marker.txt").write_text("global-db", encoding="utf-8")
    global_cron_dir = fake_home / ".bao" / "cron"
    global_cron_dir.mkdir(parents=True, exist_ok=True)
    (global_cron_dir / "jobs.json").write_text(json.dumps({"jobs": ["global"]}), encoding="utf-8")

    def fake_has_data(path: Path) -> bool:
        return path.expanduser() == custom_data_dir

    with patch("bao.profile._state_has_meaningful_data", side_effect=fake_has_data):
        ensure_profile_registry(shared_workspace, data_dir=custom_data_dir)

    default_profile = custom_data_dir / "profiles" / "default"
    assert (default_profile / "state" / "lancedb" / "marker.txt").read_text(encoding="utf-8") == "custom-db"
    assert json.loads((default_profile / "cron" / "jobs.json").read_text(encoding="utf-8")) == {
        "jobs": ["custom"]
    }


def test_profile_registry_normalizes_default_profile_id_to_default_entry(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    registry_path = fake_home / ".bao" / "profiles.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_profile_id": "work",
                "active_profile_id": "work",
                "profiles": [
                    {
                        "id": "default",
                        "display_name": "Default",
                        "storage_key": "default",
                        "avatar_key": "mochi",
                    },
                    {
                        "id": "work",
                        "display_name": "Work",
                        "storage_key": "work",
                        "avatar_key": "kiwi",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = ensure_profile_registry(shared_workspace)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    work_profile = next(profile for profile in registry.profiles if profile.display_name == "Work")

    assert registry.default_profile_id == "default"
    assert registry.active_profile_id == work_profile.id
    assert payload["default_profile_id"] == "default"


def test_set_active_profile_updates_registry(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    _, created = create_profile("Lab", shared_workspace=shared_workspace, activate=False)
    updated, context = set_active_profile(created.profile_id, shared_workspace=shared_workspace)

    assert updated.active_profile_id == created.profile_id
    assert context.profile_id == created.profile_id


def test_load_active_profile_snapshot_returns_registry_and_context(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    registry, context = load_active_profile_snapshot(shared_workspace=shared_workspace)

    assert registry.active_profile_id == "default"
    assert context.profile_id == "default"


def test_create_profile_assigns_distinct_avatar_until_pool_exhausted(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    registry = ensure_profile_registry(shared_workspace)
    seen = {registry.get("default").avatar_key}
    for index in range(1, len(PROFILE_AVATAR_KEYS)):
        registry, _ = create_profile(f"Profile {index}", shared_workspace=shared_workspace)
        seen.add(registry.profiles[-1].avatar_key)

    assert seen == set(PROFILE_AVATAR_KEYS)


def test_delete_profile_removes_non_default_and_falls_back_to_default(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    registry, context = create_profile("Lab", shared_workspace=shared_workspace)
    deleted_registry, deleted_context = delete_profile(
        context.profile_id,
        shared_workspace=shared_workspace,
    )

    assert registry.active_profile_id == context.profile_id
    assert deleted_registry.active_profile_id == "default"
    assert deleted_registry.get(context.profile_id) is None
    assert deleted_context.profile_id == "default"
    assert not context.profile_root.exists()


def test_delete_profile_keeps_default(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    registry = ensure_profile_registry(shared_workspace)
    next_registry, context = delete_profile("default", shared_workspace=shared_workspace)

    assert next_registry == registry
    assert context.profile_id == "default"


def test_rename_profile_updates_display_name_without_changing_id(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    registry, context = create_profile("Lab", shared_workspace=shared_workspace)
    renamed_registry, renamed_context = rename_profile(
        context.profile_id,
        "Research Lab",
        shared_workspace=shared_workspace,
    )

    assert registry.active_profile_id == context.profile_id
    assert renamed_registry.active_profile_id == context.profile_id
    assert renamed_registry.get(context.profile_id).display_name == "Research Lab"
    assert renamed_registry.get(context.profile_id).storage_key == context.storage_key
    assert renamed_context.profile_id == context.profile_id
    assert renamed_context.display_name == "Research Lab"
    metadata = profile_runtime_metadata(
        context.profile_id,
        shared_workspace=shared_workspace,
        registry=renamed_registry,
    )
    assert metadata["currentProfileName"] == "Research Lab"
    assert any(
        item["id"] == context.profile_id and item["displayName"] == "Research Lab"
        for item in metadata["profiles"]
    )


def test_update_profile_moves_storage_root_without_changing_id(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    (shared_workspace / "INSTRUCTIONS.md").write_text("instructions", encoding="utf-8")
    (shared_workspace / "HEARTBEAT.md").write_text("heartbeat", encoding="utf-8")

    ensure_profile_registry(shared_workspace)
    _, context = create_profile("Work", shared_workspace=shared_workspace)
    marker = context.state_root / "marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("state", encoding="utf-8")

    updated_registry, updated_context = update_profile(
        context.profile_id,
        display_name="Research",
        storage_key="research",
        shared_workspace=shared_workspace,
    )

    assert updated_context.profile_id == context.profile_id
    assert updated_context.display_name == "Research"
    assert updated_context.storage_key == "research"
    assert updated_registry.get(context.profile_id).storage_key == "research"
    assert not context.profile_root.exists()
    assert (updated_context.state_root / "marker.txt").read_text(encoding="utf-8") == "state"


def test_delete_profile_removes_updated_storage_root(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    _, context = create_profile("Work", shared_workspace=shared_workspace)
    _, updated_context = update_profile(
        context.profile_id,
        storage_key="research",
        shared_workspace=shared_workspace,
    )
    delete_profile(context.profile_id, shared_workspace=shared_workspace)

    assert not updated_context.profile_root.exists()


def test_profile_context_mapping_round_trip(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    _, context = create_profile("Work", shared_workspace=shared_workspace)

    restored = profile_context_from_mapping(profile_context_to_dict(context))

    assert restored == context
