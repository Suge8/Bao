from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ._profile_common import (
    _generate_profile_id,
    _normalize_profile_display_name,
    _normalize_profile_id,
    _now_iso,
    _pick_avatar_key,
    _replace_profile_spec,
    sanitize_profile_storage_key,
    ProfileContext,
    ProfileSpecUpdate,
    ProfileRegistry,
    ProfileSpec,
)
from ._profile_migration import _copy_profile_prompt_defaults, _ensure_profile_layout
from ._profile_runtime import profile_context, ProfileContextOptions
from ._profile_storage import _registry_operation, save_profile_registry
from ._profile_registry_ops import _ensure_profile_registry_unlocked, _profile_operation_result


@dataclass(frozen=True)
class CreateProfileOptions:
    shared_workspace: Path
    source_profile_id: str | None = None
    activate: bool = True
    data_dir: Path | None = None


@dataclass(frozen=True)
class ProfileUpdateOptions:
    shared_workspace: Path
    display_name: str | None = None
    storage_key: str | None = None
    data_dir: Path | None = None


@dataclass(frozen=True)
class RenameProfileOptions:
    shared_workspace: Path
    data_dir: Path | None = None


@dataclass(frozen=True)
class _ProfileUpdateRequest:
    profile_id: str
    display_name: str | None = None
    storage_key: str | None = None


@dataclass(frozen=True)
class _PersistProfileUpdate:
    current_context: ProfileContext
    next_context: ProfileContext
    registry: ProfileRegistry
    data_dir: Path | None = None


def create_profile(
    display_name: str,
    options: CreateProfileOptions,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(options.data_dir):
        registry = _ensure_profile_registry_unlocked(
            options.shared_workspace,
            data_dir=options.data_dir,
        )
        existing_ids = {profile.id for profile in registry.profiles}
        existing_storage_keys = {profile.storage_key for profile in registry.profiles}
        profile_id = _generate_profile_id(existing_ids)
        default_name = f"Profile {len(existing_ids) + 1}"
        name = _normalize_profile_display_name(display_name, fallback=default_name)
        storage_key = sanitize_profile_storage_key(name, existing_keys=existing_storage_keys)
        spec = ProfileSpec(
            id=profile_id,
            display_name=name,
            storage_key=storage_key,
            avatar_key=_pick_avatar_key({profile.avatar_key for profile in registry.profiles}),
            enabled=True,
            created_at=_now_iso(),
        )
        next_registry = ProfileRegistry(
            version=registry.version,
            default_profile_id=registry.default_profile_id,
            active_profile_id=profile_id if options.activate else registry.active_profile_id,
            profiles=(*registry.profiles, spec),
        )
        context = profile_context(
            profile_id,
            ProfileContextOptions(
                shared_workspace=options.shared_workspace,
                registry=next_registry,
                data_dir=options.data_dir,
            ),
        )
        _ensure_profile_layout(context)
        source_id = options.source_profile_id or registry.active_profile_id
        source_context = None
        if registry.get(source_id) is not None:
            source_context = profile_context(
                source_id,
                ProfileContextOptions(
                    shared_workspace=options.shared_workspace,
                    registry=registry,
                    data_dir=options.data_dir,
                ),
            )
        _copy_profile_prompt_defaults(source_context, context)
        try:
            save_profile_registry(next_registry, data_dir=options.data_dir)
        except Exception:
            if context.profile_root.exists():
                shutil.rmtree(context.profile_root)
            raise
        return next_registry, context


def _resolve_profile_update(
    spec: ProfileSpec,
    registry: ProfileRegistry,
    request: _ProfileUpdateRequest,
) -> tuple[str, str]:
    next_display_name = spec.display_name
    if request.display_name is not None:
        next_display_name = _normalize_profile_display_name(
            request.display_name,
            fallback=spec.display_name,
        )
    next_storage_key = spec.storage_key
    if request.storage_key is not None:
        next_storage_key = sanitize_profile_storage_key(
            request.storage_key,
            existing_keys={item.storage_key for item in registry.profiles if item.id != request.profile_id},
        )
    return next_display_name, next_storage_key


def _move_profile_root_if_needed(
    current_context: ProfileContext,
    next_context: ProfileContext,
) -> bool:
    moved_root = current_context.profile_root != next_context.profile_root
    if not moved_root or not current_context.profile_root.exists():
        return moved_root
    if next_context.profile_root.exists():
        raise FileExistsError(f"Profile storage already exists: {next_context.profile_root}")
    next_context.profile_root.parent.mkdir(parents=True, exist_ok=True)
    current_context.profile_root.replace(next_context.profile_root)
    return moved_root


def _profile_context_options(
    registry: ProfileRegistry,
    options: ProfileUpdateOptions,
) -> ProfileContextOptions:
    return ProfileContextOptions(
        shared_workspace=options.shared_workspace,
        registry=registry,
        data_dir=options.data_dir,
    )


def _build_updated_registry(
    registry: ProfileRegistry,
    request: _ProfileUpdateRequest,
) -> ProfileRegistry:
    next_profiles = tuple(
        _replace_profile_spec(
            item,
            ProfileSpecUpdate(
                display_name=request.display_name,
                storage_key=request.storage_key,
            ),
        )
        if item.id == request.profile_id
        else item
        for item in registry.profiles
    )
    return ProfileRegistry(
        version=registry.version,
        default_profile_id=registry.default_profile_id,
        active_profile_id=registry.active_profile_id,
        profiles=next_profiles,
    )


def _persist_updated_profile(state: _PersistProfileUpdate) -> None:
    moved_root = _move_profile_root_if_needed(state.current_context, state.next_context)
    _ensure_profile_layout(state.next_context)
    try:
        save_profile_registry(state.registry, data_dir=state.data_dir)
    except Exception:
        can_rollback = moved_root and state.next_context.profile_root.exists()
        if can_rollback and not state.current_context.profile_root.exists():
            state.next_context.profile_root.replace(state.current_context.profile_root)
        raise


def update_profile(
    profile_id: str,
    options: ProfileUpdateOptions,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(options.data_dir):
        registry = _ensure_profile_registry_unlocked(
            options.shared_workspace,
            data_dir=options.data_dir,
        )
        normalized_id = _normalize_profile_id(profile_id)
        spec = registry.get(normalized_id)
        if spec is None:
            return _profile_operation_result(
                registry,
                shared_workspace=options.shared_workspace,
                data_dir=options.data_dir,
            )

        next_name, next_storage_key = _resolve_profile_update(
            spec,
            registry,
            _ProfileUpdateRequest(
                profile_id=normalized_id,
                display_name=options.display_name,
                storage_key=options.storage_key,
            ),
        )
        if spec.display_name == next_name and spec.storage_key == next_storage_key:
            return _profile_operation_result(
                registry,
                shared_workspace=options.shared_workspace,
                data_dir=options.data_dir,
            )

        current_context = profile_context(normalized_id, _profile_context_options(registry, options))
        next_registry = _build_updated_registry(
            registry,
            _ProfileUpdateRequest(
                profile_id=normalized_id,
                display_name=next_name,
                storage_key=next_storage_key,
            ),
        )
        next_context = profile_context(normalized_id, _profile_context_options(next_registry, options))
        _persist_updated_profile(
            _PersistProfileUpdate(
                current_context=current_context,
                next_context=next_context,
                registry=next_registry,
                data_dir=options.data_dir,
            )
        )
        return _profile_operation_result(
            next_registry,
            shared_workspace=options.shared_workspace,
            data_dir=options.data_dir,
        )


def rename_profile(
    profile_id: str,
    display_name: str,
    options: RenameProfileOptions,
) -> tuple[ProfileRegistry, ProfileContext]:
    return update_profile(
        profile_id,
        ProfileUpdateOptions(
            shared_workspace=options.shared_workspace,
            display_name=display_name,
            data_dir=options.data_dir,
        ),
    )
