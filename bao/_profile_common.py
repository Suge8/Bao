from __future__ import annotations

import random
import re
import sys
import threading
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class ProfileSpecUpdate:
    profile_id: str | None = None
    display_name: str | None = None
    storage_key: str | None = None


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


def _normalize_profile_spec(
    raw: dict[str, Any],
    *,
    fallback_name: str,
    used_avatar_keys: set[str],
) -> ProfileSpec:
    profile_id = sanitize_profile_id(str(raw.get("id", "") or fallback_name))
    display_name = _normalize_profile_display_name(
        str(raw.get("display_name") or raw.get("displayName") or ""),
        fallback=fallback_name,
    )
    storage_key = sanitize_profile_storage_key(
        str(raw.get("storage_key") or raw.get("storageKey") or display_name or profile_id),
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


def _replace_profile_spec(spec: ProfileSpec, update: ProfileSpecUpdate) -> ProfileSpec:
    updates: dict[str, str] = {}
    if update.profile_id is not None:
        updates["id"] = update.profile_id
    if update.display_name is not None:
        updates["display_name"] = update.display_name
    if update.storage_key is not None:
        updates["storage_key"] = update.storage_key
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
                ProfileSpecUpdate(
                    profile_id=sanitize_profile_id(spec.id, existing_ids=seen_ids),
                ),
            )
        if spec.storage_key in seen_storage_keys:
            spec = _replace_profile_spec(
                spec,
                ProfileSpecUpdate(
                    storage_key=sanitize_profile_storage_key(
                        spec.storage_key,
                        existing_keys=seen_storage_keys,
                    ),
                ),
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
