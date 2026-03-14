from __future__ import annotations

import json
import os
import random
import re
import shutil
import sys
import tempfile
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

PROFILE_REGISTRY_VERSION = 1
PROFILE_BOOTSTRAP_VERSION = 1
DEFAULT_PROFILE_ID = "default"
PROFILE_AVATAR_KEYS = ("mochi", "bao", "comet", "plum", "kiwi")
_PROFILE_ID_RE = re.compile(r"[^a-z0-9]+")
_OPAQUE_PROFILE_ID_PREFIX = "prof-"
_OPAQUE_PROFILE_ID_RE = re.compile(r"^prof-[0-9a-f]{12}$")
_PROMPT_FILES = ("INSTRUCTIONS.md", "PERSONA.md", "HEARTBEAT.md")
_REGISTRY_MUTEX = threading.RLock()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir() -> Path:
    paths_module = sys.modules.get("bao.config.paths")
    if paths_module is not None:
        getter = getattr(paths_module, "get_data_dir", None)
        if callable(getter):
            return ensure_dir(Path(getter()))
    return ensure_dir(Path.home() / ".bao")


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    display_name: str
    storage_key: str
    avatar_key: str
    enabled: bool = True
    created_at: str = ""


@dataclass(frozen=True)
class ProfileRegistry:
    version: int
    default_profile_id: str
    active_profile_id: str
    profiles: tuple[ProfileSpec, ...]

    def get(self, profile_id: str) -> ProfileSpec | None:
        normalized = str(profile_id or "").strip()
        for profile in self.profiles:
            if profile.id == normalized:
                return profile
        return None


@dataclass(frozen=True)
class ProfileContext:
    profile_id: str
    display_name: str
    storage_key: str
    shared_workspace_path: Path
    profile_root: Path
    prompt_root: Path
    state_root: Path
    cron_store_path: Path
    heartbeat_file: Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_profile_spec() -> ProfileSpec:
    return ProfileSpec(
        id=DEFAULT_PROFILE_ID,
        display_name="Default",
        storage_key=DEFAULT_PROFILE_ID,
        avatar_key=random.SystemRandom().choice(PROFILE_AVATAR_KEYS),
        enabled=True,
        created_at=_now_iso(),
    )


def _default_registry() -> ProfileRegistry:
    default_profile = _default_profile_spec()
    return ProfileRegistry(
        version=PROFILE_REGISTRY_VERSION,
        default_profile_id=default_profile.id,
        active_profile_id=default_profile.id,
        profiles=(default_profile,),
    )


def _data_root(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        return get_data_dir()
    return ensure_dir(Path(data_dir).expanduser())


def _registry_path(data_dir: Path | None = None) -> Path:
    return _data_root(data_dir) / "profiles.json"


def _profiles_root(data_dir: Path | None = None) -> Path:
    return ensure_dir(_data_root(data_dir) / "profiles")


def _profile_paths(storage_key: str, *, data_dir: Path | None = None) -> tuple[Path, Path, Path, Path]:
    profile_root = _profiles_root(data_dir) / storage_key
    prompt_root = profile_root / "prompt"
    state_root = profile_root / "state"
    cron_root = profile_root / "cron"
    return profile_root, prompt_root, state_root, cron_root / "jobs.json"


def _profile_bootstrap_path(storage_key: str, *, data_dir: Path | None = None) -> Path:
    return _profiles_root(data_dir) / storage_key / ".bootstrap.json"


def _normalize_avatar_key(value: object) -> str:
    key = str(value or "").strip().lower()
    return key if key in PROFILE_AVATAR_KEYS else ""


def _pick_avatar_key(used_keys: set[str]) -> str:
    available = [key for key in PROFILE_AVATAR_KEYS if key not in used_keys]
    pool = available or list(PROFILE_AVATAR_KEYS)
    return random.SystemRandom().choice(pool)


def _sanitize_profile_key(
    value: str,
    *,
    existing_keys: set[str] | None = None,
    fallback: str = "profile",
) -> str:
    normalized = _PROFILE_ID_RE.sub("-", value.strip().lower()).strip("-")
    candidate = normalized or fallback
    occupied = existing_keys or set()
    if candidate not in occupied:
        return candidate
    suffix = 2
    while True:
        next_candidate = f"{candidate}-{suffix}"
        if next_candidate not in occupied:
            return next_candidate
        suffix += 1


def sanitize_profile_id(value: str, *, existing_ids: set[str] | None = None) -> str:
    return _sanitize_profile_key(value, existing_keys=existing_ids)


def sanitize_profile_storage_key(value: str, *, existing_keys: set[str] | None = None) -> str:
    return _sanitize_profile_key(value, existing_keys=existing_keys)


def _generate_profile_id(existing_ids: set[str]) -> str:
    while True:
        candidate = f"{_OPAQUE_PROFILE_ID_PREFIX}{uuid4().hex[:12]}"
        if candidate not in existing_ids:
            return candidate


def _normalize_profile_display_name(value: str, *, fallback: str) -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _normalize_profile_id(value: object) -> str:
    return str(value or "").strip()


def _is_opaque_profile_id(value: object) -> bool:
    return bool(_OPAQUE_PROFILE_ID_RE.fullmatch(_normalize_profile_id(value)))


def legacy_profile_id(
    *,
    current_profile_id: str,
    item_profile_id: object = "",
    snapshot_profile_id: object = "",
) -> str:
    normalized_item_id = _normalize_profile_id(item_profile_id)
    if normalized_item_id and normalized_item_id != current_profile_id:
        return normalized_item_id
    normalized_snapshot_id = _normalize_profile_id(snapshot_profile_id)
    if normalized_snapshot_id and normalized_snapshot_id != current_profile_id:
        return normalized_snapshot_id
    return ""


def rewrite_profile_scoped_id(
    value: object,
    *,
    legacy_profile_id: str,
    profile_id: str,
) -> str:
    text = _normalize_profile_id(value)
    if not text or not legacy_profile_id or legacy_profile_id == profile_id:
        return text
    if text == legacy_profile_id:
        return profile_id
    legacy_prefix = f"{legacy_profile_id}:"
    if text.startswith(legacy_prefix):
        return f"{profile_id}:{text[len(legacy_prefix):]}"
    return text


def _normalize_profile_spec(
    raw: dict[str, Any], *, fallback_name: str, used_avatar_keys: set[str]
) -> ProfileSpec:
    profile_id = sanitize_profile_id(str(raw.get("id", "") or fallback_name))
    display_name = _normalize_profile_display_name(
        str(raw.get("display_name") or raw.get("displayName") or ""),
        fallback=fallback_name,
    )
    storage_key = sanitize_profile_storage_key(
        str(raw.get("storage_key") or raw.get("storageKey") or profile_id),
    )
    avatar_key = _normalize_avatar_key(raw.get("avatar_key") or raw.get("avatarKey"))
    if not avatar_key:
        avatar_key = _pick_avatar_key(used_avatar_keys)
    used_avatar_keys.add(avatar_key)
    return ProfileSpec(
        id=profile_id,
        display_name=display_name,
        storage_key=storage_key,
        avatar_key=avatar_key,
        enabled=bool(raw.get("enabled", True)),
        created_at=str(raw.get("created_at") or raw.get("createdAt") or _now_iso()),
    )


def _replace_profile_spec(
    spec: ProfileSpec,
    *,
    profile_id: str | None = None,
    display_name: str | None = None,
    storage_key: str | None = None,
) -> ProfileSpec:
    updates: dict[str, str] = {}
    if profile_id is not None:
        updates["id"] = profile_id
    if display_name is not None:
        updates["display_name"] = display_name
    if storage_key is not None:
        updates["storage_key"] = storage_key
    return replace(spec, **updates) if updates else spec


def _make_registry(raw: dict[str, Any]) -> ProfileRegistry:
    raw_profiles = raw.get("profiles")
    items = raw_profiles if isinstance(raw_profiles, list) else []
    profiles: list[ProfileSpec] = []
    seen_ids: set[str] = set()
    seen_storage_keys: set[str] = set()
    used_avatar_keys: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        spec = _normalize_profile_spec(
            item,
            fallback_name=f"profile-{index + 1}",
            used_avatar_keys=used_avatar_keys,
        )
        if spec.id in seen_ids:
            spec = _replace_profile_spec(
                spec,
                profile_id=sanitize_profile_id(spec.id, existing_ids=seen_ids),
            )
        if spec.storage_key in seen_storage_keys:
            spec = _replace_profile_spec(
                spec,
                storage_key=sanitize_profile_storage_key(spec.storage_key, existing_keys=seen_storage_keys),
            )
        seen_ids.add(spec.id)
        seen_storage_keys.add(spec.storage_key)
        profiles.append(spec)
    if not profiles:
        profiles = [_default_profile_spec()]
    default_profile_id = str(raw.get("default_profile_id") or raw.get("defaultProfileId") or "").strip()
    if not default_profile_id or default_profile_id not in seen_ids:
        default_profile_id = profiles[0].id
    active_profile_id = str(raw.get("active_profile_id") or raw.get("activeProfileId") or "").strip()
    if not active_profile_id or active_profile_id not in seen_ids:
        active_profile_id = default_profile_id
    return ProfileRegistry(
        version=int(raw.get("version", PROFILE_REGISTRY_VERSION) or PROFILE_REGISTRY_VERSION),
        default_profile_id=default_profile_id,
        active_profile_id=active_profile_id,
        profiles=tuple(profiles),
    )


def _registry_payload(registry: ProfileRegistry) -> dict[str, Any]:
    return {
        "version": PROFILE_REGISTRY_VERSION,
        "default_profile_id": registry.default_profile_id,
        "active_profile_id": registry.active_profile_id,
        "profiles": [asdict(profile) for profile in registry.profiles],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _lock_registry_file(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        handle.write("\0")
        handle.flush()
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_registry_file(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _registry_operation(data_dir: Path | None = None):
    lock_path = _data_root(data_dir) / "profiles.lock"
    with _REGISTRY_MUTEX:
        with lock_path.open("a+", encoding="utf-8") as handle:
            _lock_registry_file(handle)
            try:
                yield
            finally:
                _unlock_registry_file(handle)


def save_profile_registry(registry: ProfileRegistry, *, data_dir: Path | None = None) -> Path:
    path = _registry_path(data_dir)
    _atomic_write_text(
        path,
        json.dumps(_registry_payload(registry), indent=2, ensure_ascii=False) + "\n",
    )
    return path


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


def profile_runtime_metadata(
    profile_id: str | None,
    *,
    display_name: str | None = None,
    shared_workspace: Path,
    registry: ProfileRegistry | None = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_registry = registry or load_profile_registry_snapshot(shared_workspace, data_dir=data_dir)
    current_spec = _resolve_runtime_profile_spec(
        profile_id=profile_id,
        display_name=display_name,
        registry=resolved_registry,
    )
    profiles = _runtime_profile_entries(resolved_registry, current_spec=current_spec)
    return {
        "currentProfileId": current_spec.id,
        "currentProfileName": current_spec.display_name,
        "profiles": profiles,
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
        peers = [name for name in peers if name]
        if peers:
            lines.append("Other profile names: " + ", ".join(peers))

    lines.append("Treat these names as the shared labels for cross-profile coordination.")
    return "\n".join(lines)


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
    if not all(
        value is not None
        for value in (
            shared_workspace,
            profile_root,
            prompt_root,
            state_root,
            cron_store_path,
            heartbeat_file,
        )
    ):
        return None
    return ProfileContext(
        profile_id=profile_id,
        display_name=str(data.get("displayName", profile_id) or profile_id).strip() or profile_id,
        storage_key=(
            str(data.get("storageKey", profile_root.name if profile_root is not None else profile_id) or profile_id).strip()
            or profile_id
        ),
        shared_workspace_path=shared_workspace,
        profile_root=profile_root,
        prompt_root=prompt_root,
        state_root=state_root,
        cron_store_path=cron_store_path,
        heartbeat_file=heartbeat_file,
    )


def _load_profile_registry(path: Path) -> tuple[ProfileRegistry, bool]:
    if not path.exists():
        return _default_registry(), True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_registry(), True
    if not isinstance(raw, dict):
        return _default_registry(), True
    loaded_registry = _make_registry(raw)
    registry = _migrate_legacy_profile_ids(loaded_registry)
    raw_profiles = raw.get("profiles")
    needs_save = any(
        isinstance(item, dict) and "storage_key" not in item and "storageKey" not in item
        for item in (raw_profiles if isinstance(raw_profiles, list) else [])
    )
    return registry, needs_save or registry != loaded_registry


def _migrate_legacy_profile_ids(registry: ProfileRegistry) -> ProfileRegistry:
    stable_ids = {
        spec.id
        for spec in registry.profiles
        if spec.id == DEFAULT_PROFILE_ID or _is_opaque_profile_id(spec.id)
    }
    id_map: dict[str, str] = {}
    next_profiles: list[ProfileSpec] = []
    changed = False
    for spec in registry.profiles:
        if spec.id == DEFAULT_PROFILE_ID or _is_opaque_profile_id(spec.id):
            stable_ids.add(spec.id)
            next_profiles.append(spec)
            continue
        next_id = _generate_profile_id(stable_ids)
        stable_ids.add(next_id)
        id_map[spec.id] = next_id
        next_profiles.append(_replace_profile_spec(spec, profile_id=next_id))
        changed = True
    if not changed:
        return registry
    return ProfileRegistry(
        version=PROFILE_REGISTRY_VERSION,
        default_profile_id=id_map.get(registry.default_profile_id, registry.default_profile_id),
        active_profile_id=id_map.get(registry.active_profile_id, registry.active_profile_id),
        profiles=tuple(next_profiles),
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
        display_name=_normalize_profile_display_name(display_name, fallback=current_spec.display_name),
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
        version=PROFILE_REGISTRY_VERSION,
        default_profile_id=registry.default_profile_id,
        active_profile_id=active_profile_id or registry.active_profile_id,
        profiles=next_profiles,
    )


def profile_context(
    profile_id: str,
    *,
    shared_workspace: Path,
    registry: ProfileRegistry | None = None,
    data_dir: Path | None = None,
) -> ProfileContext:
    resolved_registry = registry or ensure_profile_registry(shared_workspace, data_dir=data_dir)
    return _context_from_spec(
        _resolve_profile_spec(profile_id, resolved_registry),
        shared_workspace=shared_workspace,
        data_dir=data_dir,
    )


def _active_context(
    registry: ProfileRegistry,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> ProfileContext:
    return profile_context(
        registry.active_profile_id,
        shared_workspace=shared_workspace,
        registry=registry,
        data_dir=data_dir,
    )


def active_profile_context(
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> ProfileContext:
    registry = ensure_profile_registry(shared_workspace, data_dir=data_dir)
    return _active_context(registry, shared_workspace=shared_workspace, data_dir=data_dir)


def load_active_profile_snapshot(
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
        return _profile_operation_result(
            registry,
            shared_workspace=shared_workspace,
            data_dir=data_dir,
        )


def _copy_file_if_missing(source: Path, target: Path) -> bool:
    if not source.exists() or target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def _copy_tree_if_missing(source: Path, target: Path) -> bool:
    if not source.exists() or target.exists():
        return False
    shutil.copytree(source, target)
    return True


def _replace_tree(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return True


def _state_has_meaningful_data(state_root: Path) -> bool:
    try:
        from bao.session.manager import SessionManager

        session_manager = SessionManager(state_root)
        try:
            if session_manager.list_sessions():
                return True
        finally:
            session_manager.close()
    except Exception:
        return True

    try:
        from bao.agent.memory import MemoryStore

        store = MemoryStore(state_root)
        try:
            if any(not bool(item.get("is_empty", True)) for item in store.list_memory_categories()):
                return True
            if store.list_experience_items():
                return True
        finally:
            store.close()
    except Exception:
        return True
    return False


def _tree_has_entries(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def _migration_source_roots(shared_workspace: Path, *, data_dir: Path | None = None) -> tuple[Path, ...]:
    roots = [shared_workspace]
    data_root = _data_root(data_dir)
    if data_root != shared_workspace:
        roots.append(data_root)
    return tuple(roots)


def _migrate_default_state(
    shared_workspace: Path,
    state_root: Path,
    *,
    data_dir: Path | None = None,
) -> bool:
    if _state_has_meaningful_data(state_root):
        return False

    changed = False
    for source_root in _migration_source_roots(shared_workspace, data_dir=data_dir):
        source_lancedb = source_root / "lancedb"
        if source_lancedb.exists() and (
            _state_has_meaningful_data(source_root) or _tree_has_entries(source_lancedb)
        ):
            changed = _replace_tree(source_lancedb, state_root / "lancedb") or changed
            source_context = source_root / ".bao" / "context"
            if source_context.exists():
                changed = _replace_tree(source_context, state_root / ".bao" / "context") or changed
            break

    for source_root in _migration_source_roots(shared_workspace, data_dir=data_dir):
        changed = _copy_tree_if_missing(source_root / "sessions", state_root / "sessions") or changed
    return changed


def _ensure_profile_layout(context: ProfileContext) -> None:
    context.prompt_root.mkdir(parents=True, exist_ok=True)
    context.state_root.mkdir(parents=True, exist_ok=True)
    context.cron_store_path.parent.mkdir(parents=True, exist_ok=True)


def _load_profile_bootstrap_version(storage_key: str, *, data_dir: Path | None = None) -> int:
    path = _profile_bootstrap_path(storage_key, data_dir=data_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    version = payload.get("version")
    return version if isinstance(version, int) else 0


def _save_profile_bootstrap_version(storage_key: str, *, data_dir: Path | None = None) -> None:
    path = _profile_bootstrap_path(storage_key, data_dir=data_dir)
    payload = {
        "version": PROFILE_BOOTSTRAP_VERSION,
        "updated_at": _now_iso(),
    }
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def _migrate_default_profile(context: ProfileContext, *, data_dir: Path | None = None) -> bool:
    changed = False
    shared_workspace = context.shared_workspace_path.expanduser()
    _ensure_profile_layout(context)
    for filename in _PROMPT_FILES:
        changed = _copy_file_if_missing(shared_workspace / filename, context.prompt_root / filename) or changed
    changed = _migrate_default_state(shared_workspace, context.state_root, data_dir=data_dir) or changed
    legacy_cron = _data_root(data_dir) / "cron" / "jobs.json"
    changed = _copy_file_if_missing(legacy_cron, context.cron_store_path) or changed
    return changed


def _copy_profile_prompt_defaults(
    source_context: ProfileContext | None,
    target_context: ProfileContext,
) -> None:
    if source_context is None:
        return
    for filename in ("INSTRUCTIONS.md", "HEARTBEAT.md"):
        _copy_file_if_missing(source_context.prompt_root / filename, target_context.prompt_root / filename)


def _normalize_registry(registry: ProfileRegistry) -> ProfileRegistry:
    profiles = registry.profiles
    if registry.get(DEFAULT_PROFILE_ID) is None:
        profiles = (_default_profile_spec(), *profiles)
    active_profile_id = registry.active_profile_id
    return ProfileRegistry(
        version=PROFILE_REGISTRY_VERSION,
        default_profile_id=DEFAULT_PROFILE_ID,
        active_profile_id=active_profile_id if any(p.id == active_profile_id for p in profiles) else DEFAULT_PROFILE_ID,
        profiles=profiles,
    )


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
    path = _registry_path(data_dir)
    loaded_registry, _ = _load_profile_registry(path)
    return _normalize_registry(loaded_registry)


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
                shared_workspace=shared_workspace,
                registry=registry,
                data_dir=data_dir,
            )
        )
    default_profile_id = registry.default_profile_id
    default_context = profile_context(
        default_profile_id,
        shared_workspace=shared_workspace,
        registry=registry,
        data_dir=data_dir,
    )
    if _load_profile_bootstrap_version(default_context.storage_key, data_dir=data_dir) < PROFILE_BOOTSTRAP_VERSION:
        _migrate_default_profile(default_context, data_dir=data_dir)
        _save_profile_bootstrap_version(default_context.storage_key, data_dir=data_dir)
    if needs_save or registry != loaded_registry:
        save_profile_registry(registry, data_dir=data_dir)
    return registry


def _profile_operation_result(
    registry: ProfileRegistry,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    return registry, _active_context(registry, shared_workspace=shared_workspace, data_dir=data_dir)


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
            return _profile_operation_result(
                registry,
                shared_workspace=shared_workspace,
                data_dir=data_dir,
            )
        updated = _replace_registry(registry, active_profile_id=normalized_id)
        save_profile_registry(updated, data_dir=data_dir)
        return _profile_operation_result(
            updated,
            shared_workspace=shared_workspace,
            data_dir=data_dir,
        )


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
            return _profile_operation_result(
                registry,
                shared_workspace=shared_workspace,
                data_dir=data_dir,
            )

        profiles = tuple(profile for profile in registry.profiles if profile.id != normalized)
        next_active_id = registry.active_profile_id
        if next_active_id == normalized:
            next_active_id = (
                registry.default_profile_id if registry.get(registry.default_profile_id) else profiles[0].id
            )
        next_registry = _replace_registry(
            registry,
            active_profile_id=next_active_id,
            profiles=profiles,
        )

        profile_root = _profiles_root(data_dir) / spec.storage_key
        backup_root: Path | None = None
        if profile_root.exists():
            backup_root = profile_root.with_name(f".{profile_root.name}.deleting-{_now_iso().replace(':', '-')}")
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

        return _profile_operation_result(
            next_registry,
            shared_workspace=shared_workspace,
            data_dir=data_dir,
        )


def create_profile(
    display_name: str,
    *,
    shared_workspace: Path,
    source_profile_id: str | None = None,
    activate: bool = True,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
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
        next_registry = _replace_registry(
            registry,
            active_profile_id=profile_id if activate else registry.active_profile_id,
            profiles=(*registry.profiles, spec),
        )
        context = profile_context(
            profile_id,
            shared_workspace=shared_workspace,
            registry=next_registry,
            data_dir=data_dir,
        )
        _ensure_profile_layout(context)
        source_id = source_profile_id or registry.active_profile_id
        source_context = (
            profile_context(
                source_id,
                shared_workspace=shared_workspace,
                registry=registry,
                data_dir=data_dir,
            )
            if registry.get(source_id) is not None
            else None
        )
        _copy_profile_prompt_defaults(source_context, context)
        try:
            save_profile_registry(next_registry, data_dir=data_dir)
        except Exception:
            if context.profile_root.exists():
                shutil.rmtree(context.profile_root)
            raise
        return next_registry, context


def _resolve_profile_update(
    spec: ProfileSpec,
    registry: ProfileRegistry,
    *,
    profile_id: str,
    display_name: str | None = None,
    storage_key: str | None = None,
) -> tuple[str, str]:
    next_display_name = (
        spec.display_name
        if display_name is None
        else _normalize_profile_display_name(display_name, fallback=spec.display_name)
    )
    next_storage_key = spec.storage_key
    if storage_key is not None:
        next_storage_key = sanitize_profile_storage_key(
            storage_key,
            existing_keys={item.storage_key for item in registry.profiles if item.id != profile_id},
        )
    return next_display_name, next_storage_key


def update_profile(
    profile_id: str,
    *,
    shared_workspace: Path,
    display_name: str | None = None,
    storage_key: str | None = None,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    with _registry_operation(data_dir):
        registry = _ensure_profile_registry_unlocked(shared_workspace, data_dir=data_dir)
        normalized_id = _normalize_profile_id(profile_id)
        spec = registry.get(normalized_id)
        if spec is None:
            return _profile_operation_result(
                registry,
                shared_workspace=shared_workspace,
                data_dir=data_dir,
            )

        next_name, next_storage_key = _resolve_profile_update(
            spec,
            registry,
            profile_id=normalized_id,
            display_name=display_name,
            storage_key=storage_key,
        )
        if spec.display_name == next_name and spec.storage_key == next_storage_key:
            return _profile_operation_result(
                registry,
                shared_workspace=shared_workspace,
                data_dir=data_dir,
            )

        current_context = profile_context(
            normalized_id,
            shared_workspace=shared_workspace,
            registry=registry,
            data_dir=data_dir,
        )
        next_profiles = tuple(
            _replace_profile_spec(item, display_name=next_name, storage_key=next_storage_key)
            if item.id == normalized_id
            else item
            for item in registry.profiles
        )
        next_registry = _replace_registry(registry, profiles=next_profiles)
        next_context = profile_context(
            normalized_id,
            shared_workspace=shared_workspace,
            registry=next_registry,
            data_dir=data_dir,
        )

        moved_root = current_context.profile_root != next_context.profile_root and current_context.profile_root.exists()
        if moved_root:
            if next_context.profile_root.exists():
                raise FileExistsError(f"Profile storage already exists: {next_context.profile_root}")
            next_context.profile_root.parent.mkdir(parents=True, exist_ok=True)
            current_context.profile_root.replace(next_context.profile_root)
        _ensure_profile_layout(next_context)

        try:
            save_profile_registry(next_registry, data_dir=data_dir)
        except Exception:
            if moved_root and next_context.profile_root.exists() and not current_context.profile_root.exists():
                next_context.profile_root.replace(current_context.profile_root)
            raise
        return _profile_operation_result(
            next_registry,
            shared_workspace=shared_workspace,
            data_dir=data_dir,
        )


def rename_profile(
    profile_id: str,
    display_name: str,
    *,
    shared_workspace: Path,
    data_dir: Path | None = None,
) -> tuple[ProfileRegistry, ProfileContext]:
    return update_profile(
        profile_id,
        shared_workspace=shared_workspace,
        display_name=display_name,
        data_dir=data_dir,
    )
