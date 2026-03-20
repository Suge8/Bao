from __future__ import annotations

import json
import shutil
from pathlib import Path

from ._profile_common import (
    _PROMPT_FILES,
    PROFILE_BOOTSTRAP_VERSION,
    ProfileContext,
    _data_root,
    _now_iso,
    _profile_bootstrap_path,
)
from ._profile_storage import _atomic_write_text


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


def _tree_has_entries(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _has_state_data_roots(state_root: Path) -> bool:
    root = Path(state_root).expanduser()
    if not root.exists():
        return False
    candidates = (
        root / "sessions",
        root / "lancedb",
        root / ".bao" / "context",
    )
    return any(_tree_has_entries(path) for path in candidates)


def _state_has_meaningful_data(state_root: Path) -> bool:
    if not _has_state_data_roots(state_root):
        return False
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
        from bao.agent.memory import ExperienceListRequest, MemoryStore

        store = MemoryStore(state_root)
        try:
            if any(not bool(item.get("is_empty", True)) for item in store.list_memory_categories()):
                return True
            if store.list_experience_items(ExperienceListRequest()):
                return True
        finally:
            store.close()
    except Exception:
        return True
    return False


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
        has_source_data = _state_has_meaningful_data(source_root) or _tree_has_entries(source_lancedb)
        if source_lancedb.exists() and has_source_data:
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
