from __future__ import annotations

import shutil
from pathlib import Path

from ._profile_common import (
    DEFAULT_PROFILE_ID,
    PROFILE_BOOTSTRAP_VERSION,
    PROFILE_REGISTRY_VERSION,
    _default_profile_spec,
    _normalize_profile_id,
    _now_iso,
    _profiles_root,
    _registry_path,
    ProfileContext,
    ProfileRegistry,
)
from ._profile_migration import (
    _ensure_profile_layout,
    _load_profile_bootstrap_version,
    _migrate_default_profile,
    _save_profile_bootstrap_version,
)
from ._profile_runtime import _active_context, profile_context, ProfileContextOptions
from ._profile_storage import _load_profile_registry, _registry_operation, save_profile_registry


def _normalize_registry(registry: ProfileRegistry) -> ProfileRegistry:
    profiles = registry.profiles
    if registry.get(DEFAULT_PROFILE_ID) is None:
        profiles = (_default_profile_spec(), *profiles)
    active_profile_id = registry.active_profile_id
    if not any(profile.id == active_profile_id for profile in profiles):
        active_profile_id = DEFAULT_PROFILE_ID
    return ProfileRegistry(
        version=PROFILE_REGISTRY_VERSION,
        default_profile_id=DEFAULT_PROFILE_ID,
        active_profile_id=active_profile_id,
        profiles=profiles,
    )


def _profile_operation_result(
    registry: ProfileRegistry,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    return registry, _active_context(registry, shared_workspace=shared_workspace, data_dir=data_dir)


def _ensure_profile_registry_unlocked(
    shared_workspace: Path,
    *,
    data_dir: Path | None = None,
) -> ProfileRegistry:
    path = _registry_path(data_dir)
    loaded_registry, needs_save = _load_profile_registry(path)
    registry = _normalize_registry(loaded_registry)
    for spec in registry.profiles:
        _ensure_profile_layout(
            profile_context(
                spec.id,
                ProfileContextOptions(
                    shared_workspace=shared_workspace,
                    registry=registry,
                    data_dir=data_dir,
                ),
            )
        )
    default_context = profile_context(
        registry.default_profile_id,
        ProfileContextOptions(
            shared_workspace=shared_workspace,
            registry=registry,
            data_dir=data_dir,
        ),
    )
    version = _load_profile_bootstrap_version(default_context.storage_key, data_dir=data_dir)
    if version < PROFILE_BOOTSTRAP_VERSION:
        _migrate_default_profile(default_context, data_dir=data_dir)
        _save_profile_bootstrap_version(default_context.storage_key, data_dir=data_dir)
    if needs_save or registry != loaded_registry:
        save_profile_registry(registry, data_dir=data_dir)
    return registry


def ensure_profile_registry(
    shared_workspace: Path,
    *,
    data_dir: Path | None = None,
) -> ProfileRegistry:
    with _registry_operation(data_dir):
        return _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)


def load_profile_registry_snapshot(
    shared_workspace: Path,
    *,
    data_dir: Path | None = None,
) -> ProfileRegistry:
    _ = shared_workspace
    path = _registry_path(data_dir)
    loaded_registry, _ = _load_profile_registry(path)
    return _normalize_registry(loaded_registry)


def load_active_profile_snapshot(
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
        return _profile_operation_result(registry, shared_workspace=shared_workspace, data_dir=data_dir)


def set_active_profile(
    profile_id: str,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
        normalized_id = _normalize_profile_id(profile_id)
        if registry.get(normalized_id) is None or registry.active_profile_id == normalized_id:
            return _profile_operation_result(registry, shared_workspace=shared_workspace, data_dir=data_dir)
        updated = ProfileRegistry(
            version=registry.version,
            default_profile_id=registry.default_profile_id,
            active_profile_id=normalized_id,
            profiles=registry.profiles,
        )
        save_profile_registry(updated, data_dir=data_dir)
        return _profile_operation_result(updated, shared_workspace=shared_workspace, data_dir=data_dir)


def delete_profile(
    profile_id: str,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
        normalized = _normalize_profile_id(profile_id)
        spec = registry.get(normalized)
        if not normalized or normalized == DEFAULT_PROFILE_ID or spec is None:
            return _profile_operation_result(registry, shared_workspace=shared_workspace, data_dir=data_dir)

        profiles = tuple(profile for profile in registry.profiles if profile.id != normalized)
        next_active_id = registry.active_profile_id
        if next_active_id == normalized:
            default_exists = registry.get(registry.default_profile_id) is not None
            next_active_id = registry.default_profile_id if default_exists else profiles[0].id
        next_registry = ProfileRegistry(
            version=registry.version,
            default_profile_id=registry.default_profile_id,
            active_profile_id=next_active_id,
            profiles=profiles,
        )
        profile_root = _profiles_root(data_dir) / spec.storage_key
        backup_root: Path | None = None
        if profile_root.exists():
            stamp = _now_iso().replace(":", "-")
            backup_root = profile_root.with_name(f".{profile_root.name}.deleting-{stamp}")
            if backup_root.exists():
                shutil.rmtree(backup_root)
            profile_root.replace(backup_root)
        try:
            save_profile_registry(next_registry, data_dir=data_dir)
        except Exception:
            if backup_root is not None and backup_root.exists():
                backup_root.replace(profile_root)
            raise
        if backup_root is not None and backup_root.exists():
            shutil.rmtree(backup_root)
        return _profile_operation_result(next_registry, shared_workspace=shared_workspace, data_dir=data_dir)
