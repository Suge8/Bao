"""Runtime path helpers derived from the active config context."""

from __future__ import annotations

from pathlib import Path

_runtime_config_path: Path | None = None


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def set_runtime_config_path(path: str | Path | None) -> None:
    global _runtime_config_path
    if path is None:
        _runtime_config_path = None
        return
    _runtime_config_path = Path(path).expanduser()


def _default_root() -> Path:
    return Path.home() / ".bao"


def get_default_data_dir() -> Path:
    return ensure_dir(_default_root())


def get_config_path() -> Path:
    override = _runtime_config_path
    if override is not None:
        return override
    base = get_default_data_dir()
    jsonc = base / "config.jsonc"
    if jsonc.exists():
        return jsonc
    return base / "config.json"


def get_data_dir() -> Path:
    return ensure_dir(get_config_path().parent)


def get_runtime_subdir(name: str) -> Path:
    return ensure_dir(get_data_dir() / name)


def get_media_dir(channel: str | None = None) -> Path:
    base = get_runtime_subdir("media")
    return ensure_dir(base / channel) if channel else base


def get_workspace_path(workspace: str | None = None) -> Path:
    path = Path(workspace).expanduser() if workspace else get_data_dir() / "workspace"
    return ensure_dir(path)


def get_cli_history_path() -> Path:
    return get_runtime_subdir("history") / "cli_history"


def get_bridge_install_dir() -> Path:
    return get_data_dir() / "bridge"
