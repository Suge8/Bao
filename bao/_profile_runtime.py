from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._profile_common import (
    DEFAULT_PROFILE_ID,
    _normalize_profile_display_name,
    _profile_paths,
    _replace_profile_spec,
    ProfileContext,
    ProfileSpecUpdate,
    ProfileRegistry,
    ProfileSpec,
)


@dataclass(frozen=True)
class ProfileContextOptions:
    shared_workspace: Path
    registry: ProfileRegistry | None = None
    data_dir: Path | None = None


@dataclass(frozen=True)
class ProfileRuntimeMetadataOptions:
    shared_workspace: Path
    display_name: str | None = None
    registry: ProfileRegistry | None = None
    data_dir: Path | None = None


def profile_context_to_dict(context: ProfileContext | None) -> dict[str, str]:
    if context is None:
        return {}
    return {
        "profileId": context.profile_id,
        "displayName": context.display_name,
        "storageKey": context.storage_key,
        "sharedWorkspacePath": str(context.shared_workspace_path),
        "profileRoot": str(context.profile_root),
        "promptRoot": str(context.prompt_root),
        "stateRoot": str(context.state_root),
        "cronStorePath": str(context.cron_store_path),
        "heartbeatFile": str(context.heartbeat_file),
    }


def profile_context_from_mapping(data: Mapping[str, object] | None) -> ProfileContext | None:
    if data is None:
        return None
    profile_id = str(data.get("profileId", "") or "").strip()
    if not profile_id:
        return None

    def _path(key: str) -> Path | None:
        raw = str(data.get(key, "") or "").strip()
        return Path(raw).expanduser() if raw else None

    shared_workspace = _path("sharedWorkspacePath")
    profile_root = _path("profileRoot")
    prompt_root = _path("promptRoot")
    state_root = _path("stateRoot")
    cron_store_path = _path("cronStorePath")
    heartbeat_file = _path("heartbeatFile")
    values = (
        shared_workspace,
        profile_root,
        prompt_root,
        state_root,
        cron_store_path,
        heartbeat_file,
    )
    if not all(value is not None for value in values):
        return None
    fallback_storage_key = profile_root.name if profile_root is not None else profile_id
    return ProfileContext(
        profile_id=profile_id,
        display_name=str(data.get("displayName", profile_id) or profile_id).strip() or profile_id,
        storage_key=str(data.get("storageKey", fallback_storage_key) or profile_id).strip() or profile_id,
        shared_workspace_path=shared_workspace,
        profile_root=profile_root,
        prompt_root=prompt_root,
        state_root=state_root,
        cron_store_path=cron_store_path,
        heartbeat_file=heartbeat_file,
    )


def _resolve_profile_spec(profile_id: str, registry: ProfileRegistry) -> ProfileSpec:
    spec = registry.get(profile_id) or registry.get(registry.default_profile_id)
    assert spec is not None
    return spec


def _resolve_runtime_profile_spec(
    *,
    profile_id: str | None,
    display_name: str | None,
    registry: ProfileRegistry,
) -> ProfileSpec:
    normalized_profile_id = str(profile_id or registry.active_profile_id or "").strip()
    current_spec = registry.get(normalized_profile_id)
    if current_spec is None:
        fallback_id = normalized_profile_id or DEFAULT_PROFILE_ID
        return ProfileSpec(
            id=fallback_id,
            display_name=_normalize_profile_display_name(display_name or fallback_id, fallback=fallback_id),
            storage_key=fallback_id,
            avatar_key="",
        )
    if display_name is None:
        return current_spec
    return _replace_profile_spec(
        current_spec,
        ProfileSpecUpdate(
            display_name=_normalize_profile_display_name(
                display_name,
                fallback=current_spec.display_name,
            ),
        ),
    )


def _runtime_profile_entry(spec: ProfileSpec, *, is_current: bool) -> dict[str, Any]:
    return {
        "id": spec.id,
        "displayName": spec.display_name,
        "storageKey": spec.storage_key,
        "isCurrent": is_current,
    }


def _runtime_profile_entries(
    registry: ProfileRegistry,
    *,
    current_spec: ProfileSpec,
) -> list[dict[str, Any]]:
    profiles = [
        _runtime_profile_entry(spec, is_current=spec.id == current_spec.id)
        for spec in registry.profiles
    ]
    for item in profiles:
        if item["id"] == current_spec.id:
            item["displayName"] = current_spec.display_name
            item["isCurrent"] = True
            return profiles
    profiles.insert(0, _runtime_profile_entry(current_spec, is_current=True))
    return profiles


def _context_from_spec(
    spec: ProfileSpec,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> ProfileContext:
    profile_root, prompt_root, state_root, cron_store_path = _profile_paths(
        spec.storage_key,
        data_dir=data_dir,
    )
    return ProfileContext(
        profile_id=spec.id,
        display_name=spec.display_name,
        storage_key=spec.storage_key,
        shared_workspace_path=shared_workspace.expanduser(),
        profile_root=profile_root,
        prompt_root=prompt_root,
        state_root=state_root,
        cron_store_path=cron_store_path,
        heartbeat_file=prompt_root / "HEARTBEAT.md",
    )


def _replace_registry(
    registry: ProfileRegistry,
    *,
    active_profile_id: str | None = None,
    profiles: tuple[ProfileSpec, ...] | None = None,
) -> ProfileRegistry:
    next_profiles = profiles or registry.profiles
    return ProfileRegistry(
        version=registry.version,
        default_profile_id=registry.default_profile_id,
        active_profile_id=active_profile_id or registry.active_profile_id,
        profiles=next_profiles,
    )


def profile_context(profile_id: str, options: ProfileContextOptions) -> ProfileContext:
    resolved_registry = options.registry
    if resolved_registry is None:
        from ._profile_ops import ensure_profile_registry

        resolved_registry = ensure_profile_registry(
            options.shared_workspace,
            data_dir=options.data_dir,
        )
    return _context_from_spec(
        _resolve_profile_spec(profile_id, resolved_registry),
        shared_workspace=options.shared_workspace,
        data_dir=options.data_dir,
    )


def _active_context(
    registry: ProfileRegistry,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> ProfileContext:
    return profile_context(
        registry.active_profile_id,
        ProfileContextOptions(
            shared_workspace=shared_workspace,
            registry=registry,
            data_dir=data_dir,
        ),
    )


def active_profile_context(
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> ProfileContext:
    from ._profile_ops import ensure_profile_registry

    registry = ensure_profile_registry(shared_workspace, data_dir=data_dir)
    return _active_context(registry, shared_workspace=shared_workspace, data_dir=data_dir)


def profile_runtime_metadata(
    profile_id: str | None,
    options: ProfileRuntimeMetadataOptions,
) -> dict[str, Any]:
    resolved_registry = options.registry
    if resolved_registry is None:
        from ._profile_ops import load_profile_registry_snapshot

        resolved_registry = load_profile_registry_snapshot(
            options.shared_workspace,
            data_dir=options.data_dir,
        )
    current_spec = _resolve_runtime_profile_spec(
        profile_id=profile_id,
        display_name=options.display_name,
        registry=resolved_registry,
    )
    return {
        "currentProfileId": current_spec.id,
        "currentProfileName": current_spec.display_name,
        "profiles": _runtime_profile_entries(resolved_registry, current_spec=current_spec),
    }


def format_profile_runtime_block(profile_metadata: Mapping[str, object] | None) -> str:
    if not isinstance(profile_metadata, Mapping):
        return ""
    current_name = str(profile_metadata.get("currentProfileName", "") or "").strip()
    raw_profiles = profile_metadata.get("profiles")
    if not current_name and not isinstance(raw_profiles, list):
        return ""
    lines: list[str] = []
    if current_name:
        lines.append(f"Current profile name: {current_name}")
    if isinstance(raw_profiles, list):
        peers = [
            str(item.get("displayName", "") or "").strip()
            for item in raw_profiles
            if isinstance(item, Mapping) and not bool(item.get("isCurrent", False))
        ]
        names = [name for name in peers if name]
        if names:
            lines.append("Other profile names: " + ", ".join(names))
    lines.append("Treat these names as the shared labels for cross-profile coordination.")
    return "\n".join(lines)
