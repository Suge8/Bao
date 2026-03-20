"""Tests for ensure_first_run() and load_config() first-run behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bao.config._loader_helpers import strip_jsonc_comments
from bao.config.loader import ensure_first_run, get_config_path, load_config, save_config
from bao.config.migrations import CURRENT_VERSION
from bao.config.paths import get_media_dir, get_workspace_path, set_runtime_config_path


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """Redirect Path.home() + HOME env to tmp_path."""
    set_runtime_config_path(None)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path
    set_runtime_config_path(None)


def test_ensure_first_run_creates_files(fake_home):
    """First call creates config.jsonc + workspace dir, returns True."""
    result = ensure_first_run()

    assert result is True
    config_path = fake_home / ".bao" / "config.jsonc"
    assert config_path.exists()
    text = config_path.read_text(encoding="utf-8")
    assert f'"config_version": {CURRENT_VERSION}' in text
    assert (fake_home / ".bao" / "workspace").is_dir()
    assert (fake_home / ".bao" / "profiles.json").exists()


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


def test_load_config_migration_rewrites_jsonc_with_comments(fake_home):
    config_path = fake_home / ".bao" / "config.jsonc"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """{
  "config_version": 5,
  "tools": {
    "toolExposure": {
      "mode": "off",
      "bundles": ["core", "web", "code"]
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  },
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test"
    }
  }
}""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    rewritten = config_path.read_text(encoding="utf-8")
    assert config.tools.tool_exposure.domains == [
        "core",
        "messaging",
        "handoff",
        "web_research",
        "coding_backend",
    ]
    assert "// 工具暴露策略 | Tool exposure policy" in rewritten
    assert '"domains": [' in rewritten
    assert '"bundles"' not in rewritten


def test_save_config_existing_file_restores_template_comments(fake_home):
    ensure_first_run()
    config_path = fake_home / ".bao" / "config.jsonc"
    config_path.write_text(
        '{"config_version": 6, "agents": {"defaults": {"model": "openai/gpt-4o"}}}',
        encoding="utf-8",
    )

    save_config(load_config(config_path), config_path)

    rewritten = config_path.read_text(encoding="utf-8")
    assert "//  🤖 Agent 配置 | Agent Settings" in rewritten
    assert "// 工具暴露策略 | Tool exposure policy" in rewritten
    assert '"model": "openai/gpt-4o"' in rewritten
    assert '"experienceModel"' not in rewritten
    assert '"memoryWindow"' not in rewritten


def test_save_config_prunes_default_runtime_noise(fake_home):
    config_path = fake_home / ".bao" / "config.jsonc"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """{
  "config_version": 6,
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  },
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test",
      "type": "openai",
      "extraHeaders": {}
    }
  },
  "channels": {
    "mochat": {
      "enabled": false,
      "baseUrl": "",
      "socketPath": ""
    }
  }
}""",
        encoding="utf-8",
    )

    save_config(load_config(config_path), config_path)

    rewritten = config_path.read_text(encoding="utf-8")
    assert '"toolOutputPreviewChars"' not in rewritten
    assert '"artifactRetentionDays"' not in rewritten
    assert '"pathAppend"' not in rewritten
    assert '"retryAttempts"' not in rewritten
    assert '"hub": {' not in rewritten
    assert '"extraHeaders"' not in rewritten
    parsed = json.loads(strip_jsonc_comments(rewritten))
    assert "type" not in parsed["providers"]["openaiCompatible"]
    assert parsed["channels"].get("mochat") in ({}, {"enabled": False}, None)


def test_get_config_path_uses_shared_data_root(fake_home):
    config_path = get_config_path()

    assert config_path == fake_home / ".bao" / "config.json"


def test_get_media_dir_uses_shared_data_root(fake_home):
    media_path = get_media_dir()

    assert media_path == fake_home / ".bao" / "media"
    assert media_path.is_dir()


def test_get_workspace_path_uses_runtime_data_root(tmp_path):
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        workspace_path = get_workspace_path()

        assert workspace_path == tmp_path / "workspace"
        assert workspace_path.is_dir()
    finally:
        set_runtime_config_path(None)
