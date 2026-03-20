# ruff: noqa: F403, F405
from __future__ import annotations

from tests._profile_registry_testkit import *


def test_create_profile_clones_shared_prompt_defaults_without_persona(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)
    (shared_workspace / "INSTRUCTIONS.md").write_text("instructions", encoding="utf-8")
    (shared_workspace / "PERSONA.md").write_text("persona", encoding="utf-8")
    (shared_workspace / "HEARTBEAT.md").write_text("heartbeat", encoding="utf-8")

    ensure_profile_registry(shared_workspace)
    registry, context = create_profile(
        "Work Mode",
        CreateProfileOptions(shared_workspace=shared_workspace),
    )

    assert registry.active_profile_id == context.profile_id
    assert re.fullmatch(r"prof-[0-9a-f]{12}", context.profile_id)
    assert context.storage_key == "work-mode"
    assert registry.get(context.profile_id).avatar_key in PROFILE_AVATAR_KEYS
    assert (context.prompt_root / "INSTRUCTIONS.md").read_text(encoding="utf-8") == "instructions"
    assert (context.prompt_root / "HEARTBEAT.md").read_text(encoding="utf-8") == "heartbeat"
    assert not (context.prompt_root / "PERSONA.md").exists()


def test_create_profile_assigns_distinct_avatar_until_pool_exhausted(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    registry = ensure_profile_registry(shared_workspace)
    seen = {registry.get("default").avatar_key}
    for index in range(1, len(PROFILE_AVATAR_KEYS)):
        registry, _ = create_profile(
            f"Profile {index}",
            CreateProfileOptions(shared_workspace=shared_workspace),
        )
        seen.add(registry.profiles[-1].avatar_key)

    assert seen == set(PROFILE_AVATAR_KEYS)


def test_delete_profile_removes_non_default_and_falls_back_to_default(fake_home: Path) -> None:
    shared_workspace = fake_home / ".bao" / "workspace"
    shared_workspace.mkdir(parents=True, exist_ok=True)

    ensure_profile_registry(shared_workspace)
    registry, context = create_profile("Lab", CreateProfileOptions(shared_workspace=shared_workspace))
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
    registry, context = create_profile("Lab", CreateProfileOptions(shared_workspace=shared_workspace))
    renamed_registry, renamed_context = rename_profile(
        context.profile_id,
        "Research Lab",
        RenameProfileOptions(shared_workspace=shared_workspace),
    )

    assert registry.active_profile_id == context.profile_id
    assert renamed_registry.active_profile_id == context.profile_id
    assert renamed_registry.get(context.profile_id).display_name == "Research Lab"
    assert renamed_registry.get(context.profile_id).storage_key == context.storage_key
    assert renamed_context.profile_id == context.profile_id
    assert renamed_context.display_name == "Research Lab"
    metadata = profile_runtime_metadata(
        context.profile_id,
        ProfileRuntimeMetadataOptions(
            shared_workspace=shared_workspace,
            registry=renamed_registry,
        ),
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
    _, context = create_profile("Work", CreateProfileOptions(shared_workspace=shared_workspace))
    marker = context.state_root / "marker.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("state", encoding="utf-8")

    updated_registry, updated_context = update_profile(
        context.profile_id,
        ProfileUpdateOptions(
            shared_workspace=shared_workspace,
            display_name="Research",
            storage_key="research",
        ),
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
    _, context = create_profile("Work", CreateProfileOptions(shared_workspace=shared_workspace))
    _, updated_context = update_profile(
        context.profile_id,
        ProfileUpdateOptions(
            shared_workspace=shared_workspace,
            storage_key="research",
        ),
    )
    delete_profile(context.profile_id, shared_workspace=shared_workspace)

    assert not updated_context.profile_root.exists()
