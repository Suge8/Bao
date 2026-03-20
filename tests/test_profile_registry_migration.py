# ruff: noqa: F403, F405
from __future__ import annotations

from tests._profile_registry_testkit import *


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


def test_profile_registry_repairs_invalid_registry_file(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    registry_path = fake_home / ".bao" / "profiles.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{invalid", encoding="utf-8")

    registry = ensure_profile_registry(shared_workspace)

    assert registry.default_profile_id == "default"
    assert json.loads(registry_path.read_text(encoding="utf-8"))["default_profile_id"] == "default"


def test_profile_registry_backfills_storage_key_without_rewriting_ids(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    registry_path = fake_home / ".bao" / "profiles.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_profile_id": "default",
                "active_profile_id": "prof-123456789abc",
                "profiles": [
                    {
                        "id": "default",
                        "display_name": "Default",
                        "avatar_key": "mochi",
                        "enabled": True,
                    },
                    {
                        "id": "prof-123456789abc",
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
    assert work_profile.id == "prof-123456789abc"
    assert work_profile.storage_key == "work"
    assert registry.active_profile_id == "prof-123456789abc"
    assert payload["profiles"][0]["storage_key"] == "default"
    assert payload["profiles"][1]["id"] == "prof-123456789abc"
    assert payload["profiles"][1]["storage_key"] == "work"
    assert payload["active_profile_id"] == "prof-123456789abc"


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

    with patch("bao._profile_migration._state_has_meaningful_data", side_effect=fake_has_data):
        ensure_profile_registry(shared_workspace)

    assert (target_lancedb / "marker.txt").read_text(encoding="utf-8") == "workspace-db"
    assert not (target_lancedb / "placeholder.txt").exists()


def test_state_data_roots_ignore_non_directory_placeholders(fake_home: Path) -> None:
    state_root = fake_home / ".bao" / "profiles" / "default" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "lancedb").write_text("not-a-directory", encoding="utf-8")

    assert _has_state_data_roots(state_root) is False


def test_profile_registry_skips_default_state_scan_after_bootstrap(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)

    with patch(
        "bao._profile_migration._state_has_meaningful_data",
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

    with patch("bao._profile_migration._state_has_meaningful_data", side_effect=fake_has_data):
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
