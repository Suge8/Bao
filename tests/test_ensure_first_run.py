"""Tests for ensure_first_run() and load_config() first-run behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from bao.config.loader import ensure_first_run, get_config_path, load_config
from bao.utils.helpers import get_media_path


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Redirect Path.home() + HOME env to tmp_path."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_ensure_first_run_creates_files(fake_home):
    """First call creates config.jsonc + workspace dir, returns True."""
    result = ensure_first_run()

    assert result is True
    config_path = fake_home / ".bao" / "config.jsonc"
    assert config_path.exists()
    text = config_path.read_text(encoding="utf-8")
    assert '"config_version": 3' in text
    assert (fake_home / ".bao" / "workspace").is_dir()


def test_ensure_first_run_idempotent(fake_home):
    """Second call returns False without overwriting existing config."""
    ensure_first_run()
    config_path = fake_home / ".bao" / "config.jsonc"
    original_content = config_path.read_text(encoding="utf-8")
    mtime_before = config_path.stat().st_mtime

    result = ensure_first_run()

    assert result is False
    assert config_path.read_text(encoding="utf-8") == original_content
    assert config_path.stat().st_mtime == mtime_before


def test_load_config_first_run_exits(fake_home):
    """load_config() on missing config calls ensure_first_run then SystemExit(0)."""
    with pytest.raises(SystemExit) as exc_info:
        load_config()

    assert exc_info.value.code == 0
    assert (fake_home / ".bao" / "config.jsonc").exists()
    assert (fake_home / ".bao" / "workspace").is_dir()


def test_get_config_path_uses_shared_data_root(fake_home):
    config_path = get_config_path()

    assert config_path == fake_home / ".bao" / "config.json"


def test_get_media_path_uses_shared_data_root(fake_home):
    media_path = get_media_path()

    assert media_path == fake_home / ".bao" / "media"
    assert media_path.is_dir()
