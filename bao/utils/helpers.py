"""Utility functions for Bao."""

from datetime import datetime
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    """Get the Bao data directory (~/.bao)."""
    return ensure_dir(Path.home() / ".bao")


def get_data_subdir(*parts: str) -> Path:
    return ensure_dir(get_data_path().joinpath(*parts))


def get_media_path() -> Path:
    return get_data_subdir("media")


def timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    # Replace unsafe characters
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()
