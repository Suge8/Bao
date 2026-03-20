# ruff: noqa: F403, F405
from __future__ import annotations

from tests._coding_agent_skill_testkit import *


class TestSetupScript:
    def test_creates_config_in_empty_dir(self, tmp_path):
        result = subprocess.run(
            [str(SETUP_SCRIPT), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        config_file = tmp_path / "opencode.json"
        assert config_file.is_file()
        config = json.loads(config_file.read_text())
        assert config["permission"]["edit"] == "allow"
        assert config["permission"]["bash"] == "allow"
        assert "$schema" in config

    def test_creates_config_with_model(self, tmp_path):
        result = subprocess.run(
            [str(SETUP_SCRIPT), str(tmp_path), "--model", "anthropic/claude-sonnet-4-20250514"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        config = json.loads((tmp_path / "opencode.json").read_text())
        assert config["model"] == "anthropic/claude-sonnet-4-20250514"
        assert config["permission"]["edit"] == "allow"

    def test_skips_existing_config(self, tmp_path):
        existing = tmp_path / "opencode.json"
        existing.write_text('{"custom": true}')
        result = subprocess.run(
            [str(SETUP_SCRIPT), str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "already exists" in result.stdout
        assert json.loads(existing.read_text()) == {"custom": True}

    def test_fails_on_missing_dir(self):
        result = subprocess.run(
            [str(SETUP_SCRIPT), "/nonexistent/path/xyz"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "does not exist" in result.stderr

    def test_fails_without_args(self):
        result = subprocess.run(
            [str(SETUP_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_help_flag(self):
        result = subprocess.run(
            [str(SETUP_SCRIPT), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout
