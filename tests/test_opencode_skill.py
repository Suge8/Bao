"""Tests for the opencode skill."""

import json
import os
import subprocess
from pathlib import Path

from bao.agent.skills import SkillsLoader

SKILL_DIR = Path(__file__).parent.parent / "bao" / "skills"
OPENCODE_SKILL_DIR = SKILL_DIR / "opencode"
SETUP_SCRIPT = OPENCODE_SKILL_DIR / "scripts" / "setup-project.sh"


# ---------------------------------------------------------------------------
# Skill metadata & loading
# ---------------------------------------------------------------------------


class TestSkillMetadata:
    """Verify SKILL.md frontmatter and discoverability."""

    def test_skill_directory_exists(self):
        assert OPENCODE_SKILL_DIR.is_dir()

    def test_skill_md_exists(self):
        assert (OPENCODE_SKILL_DIR / "SKILL.md").is_file()

    def test_scripts_directory_exists(self):
        assert (OPENCODE_SKILL_DIR / "scripts").is_dir()

    def test_setup_script_exists_and_executable(self):
        assert SETUP_SCRIPT.is_file()
        assert os.access(SETUP_SCRIPT, os.X_OK)

    def test_skill_discovered_by_loader(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        skills = loader.list_skills(filter_unavailable=False)
        names = [s["name"] for s in skills]
        assert "opencode" in names

    def test_skill_has_valid_metadata(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        meta = loader.get_skill_metadata("opencode")
        assert meta is not None
        assert meta.get("name") == "opencode"
        assert (
            "coding" in meta.get("description", "").lower()
            or "code" in meta.get("description", "").lower()
        )

    def test_skill_content_loads(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        content = loader.load_skill("opencode")
        assert content is not None
        assert "opencode run" in content
        assert "--continue" in content

    def test_skill_requires_opencode_bin(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        meta = loader.get_skill_metadata("opencode")
        assert meta is not None
        raw = meta.get("metadata", "")
        parsed = json.loads(raw) if isinstance(raw, str) and raw else {}
        bao_meta = parsed.get("bao", {})
        requires = bao_meta.get("requires", {})
        assert "opencode" in requires.get("bins", [])


# ---------------------------------------------------------------------------
# Setup script tests
# ---------------------------------------------------------------------------


class TestSetupScript:
    """Verify setup-project.sh creates valid opencode.json."""

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
        # Original content preserved
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
