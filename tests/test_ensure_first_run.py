"""Tests for ensure_first_run() and load_config() first-run behavior."""

from __future__ import annotations

import pytest
from pathlib import Path

from bao.config.loader import ensure_first_run, load_config


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
    assert (fake_home / ".bao" / "config.jsonc").exists()
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
