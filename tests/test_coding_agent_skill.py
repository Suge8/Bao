"""Tests for the unified coding-agent skill."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bao.agent.skills import SkillsLoader

SKILL_DIR = Path(__file__).parent.parent / "bao" / "skills"
CODING_AGENT_SKILL_DIR = SKILL_DIR / "coding-agent"
AGENT_BROWSER_SKILL_DIR = SKILL_DIR / "agent-browser"
SETUP_SCRIPT = CODING_AGENT_SKILL_DIR / "scripts" / "setup-project.sh"


# ---------------------------------------------------------------------------
# Skill metadata & loading
# ---------------------------------------------------------------------------


class TestSkillMetadata:
    """Verify SKILL.md frontmatter and discoverability."""

    def test_skill_directory_exists(self):
        assert CODING_AGENT_SKILL_DIR.is_dir()

    def test_skill_md_exists(self):
        assert (CODING_AGENT_SKILL_DIR / "SKILL.md").is_file()

    def test_scripts_directory_exists(self):
        assert (CODING_AGENT_SKILL_DIR / "scripts").is_dir()

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
        assert "coding-agent" in names

    def test_skill_has_valid_metadata(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        meta = loader.get_skill_metadata("coding-agent")
        assert meta is not None
        assert meta.get("name") == "coding-agent"
        assert (
            "coding" in meta.get("description", "").lower()
            or "code" in meta.get("description", "").lower()
        )

    def test_skill_content_loads(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        content = loader.load_skill("coding-agent")
        assert content is not None
        assert "coding_agent" in content
        assert "continue_session" in content

    def test_skill_requires_bins_any(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        meta = loader.get_skill_metadata("coding-agent")
        assert meta is not None
        raw = meta.get("metadata", "")
        parsed = json.loads(raw) if isinstance(raw, str) and raw else {}
        bao_meta = parsed.get("bao", {})
        requires = bao_meta.get("requires", {})
        bins_any = requires.get("bins_any", [])
        assert "opencode" in bins_any
        assert "codex" in bins_any
        assert "claude" in bins_any

    def test_agent_browser_skill_has_required_cli_metadata(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        meta = loader.get_skill_metadata("agent-browser")
        assert meta is not None
        raw = meta.get("metadata", "")
        parsed = json.loads(raw) if isinstance(raw, str) and raw else {}
        bao_meta = parsed.get("bao", {})
        requires = bao_meta.get("requires", {})
        bins = requires.get("bins", [])
        assert "agent-browser" in bins

    def test_agent_browser_skill_content_prefers_builtin_tool(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        content = loader.load_skill("agent-browser")
        assert content is not None
        assert "agent_browser" in content
        assert "If `agent_browser` is present in `## Available Now`" in content

    def test_workspace_skill_content_cache_reuses_file_until_it_changes(self, tmp_path):
        skill_dir = tmp_path / "skills" / "demo-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        _ = skill_file.write_text("---\nname: demo-skill\n---\n\nfirst\n", encoding="utf-8")

        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        assert loader.load_skill("demo-skill") is not None

        original_read_text = Path.read_text

        def _fail_cached_read(self: Path, *args, **kwargs):
            if self == skill_file:
                raise AssertionError("skill content should be served from cache")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", _fail_cached_read):
            assert loader.load_skill("demo-skill") == "---\nname: demo-skill\n---\n\nfirst\n"

        _ = skill_file.write_text("---\nname: demo-skill\n---\n\nsecond\n", encoding="utf-8")
        assert loader.load_skill("demo-skill") == "---\nname: demo-skill\n---\n\nsecond\n"

    def test_workspace_skill_cache_invalidates_when_stat_signature_changes(self, tmp_path):
        skill_dir = tmp_path / "skills" / "demo-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        _ = skill_file.write_text("---\nname: demo-skill\n---\n\nfirst\n", encoding="utf-8")

        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        assert loader.load_skill("demo-skill") == "---\nname: demo-skill\n---\n\nfirst\n"

        current_stat = skill_file.stat()
        updated = "---\nname: demo-skill\n---\n\nsecond\n"
        original_read_text = Path.read_text
        original_stat = Path.stat

        def _patched_stat(self: Path):
            if self == skill_file:
                return SimpleNamespace(
                    st_mtime_ns=current_stat.st_mtime_ns,
                    st_ctime_ns=current_stat.st_ctime_ns + 1,
                    st_size=len(updated.encode("utf-8")),
                )
            return original_stat(self)

        def _patched_read_text(self: Path, *args, **kwargs):
            if self == skill_file:
                return updated
            return original_read_text(self, *args, **kwargs)

        with (
            patch.object(Path, "stat", _patched_stat),
            patch.object(Path, "read_text", _patched_read_text),
        ):
            assert loader.load_skill("demo-skill") == updated

    def test_summary_contains_high_signal_trigger_phrases(self, tmp_path):
        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )
        summary = loader.build_skills_summary()

        expected_prefixes = {
            "agent-browser": "Use for browser automation, screenshots, form",
            "clawhub": "Use to find, install, or update skills from ClawHub",
            "coding-agent": "Use for general coding tasks when no more specific coding",
            "copywriting": "Use for marketing copy, headlines, CTAs, and page",
            "cron": "Use to schedule reminders, recurring tasks, or one-time",
            "docx": "Use for Word docs, reports, memos, letters, contracts",
            "find-skills": "Use when asked to find, install, or recommend",
            "github": "Use for GitHub issues, PRs, Actions, releases, or repo",
            "image-gen": "Use to draw, generate, design, or create images",
            "memory": "Use for memory recall, consolidation, preferences, or",
            "pdf": "Use for PDFs, scans, OCR, forms, extraction, merge",
            "pptx": "Use for slides, decks, presentations, pitch decks",
            "skill-creator": "Use to create, update, package, or structure a",
            "summarize": "Use to summarize URLs, files, podcasts, videos, or",
            "tmux": "Use for interactive terminal sessions, TUI apps, or",
            "weather": "Use for current weather, forecasts, or weather",
            "xlsx": "Use for spreadsheets, Excel, CSV/TSV cleanup, tables",
        }

        for skill_name, prefix in expected_prefixes.items():
            assert f"{skill_name} — {prefix}" in summary

        assert '<skill path="' in summary
        assert 'source="builtin" available="true">docx — Use for Word docs' in summary

    def test_workspace_skills_are_marked_with_workspace_source_in_summary(self, tmp_path):
        skill_dir = tmp_path / "skills" / "demo-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: Use for demo workflow tasks.\n---\n\n# Demo\n",
            encoding="utf-8",
        )

        loader = SkillsLoader(
            workspace=tmp_path,
            builtin_skills_dir=SKILL_DIR,
        )

        summary = loader.build_skills_summary()
        assert '<skill path="' in summary
        assert (
            'source="workspace" available="true">demo-skill — Use for demo workflow tasks.'
            in summary
        )


# ---------------------------------------------------------------------------
# bins_any requirement logic
# ---------------------------------------------------------------------------


class TestBinsAnyRequirements:
    """Verify _check_requirements handles bins_any correctly."""

    def test_bins_any_available_when_one_exists(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: "/usr/bin/opencode" if b == "opencode" else original_which(b),
        )
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "coding-agent" in names

    def test_bins_any_unavailable_when_none_exist(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b in ("opencode", "codex", "claude") else original_which(b),
        )
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "coding-agent" not in names

    def test_missing_requirements_message_for_bins_any(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b in ("opencode", "codex", "claude") else original_which(b),
        )
        meta = loader._get_skill_meta("coding-agent")
        msg = loader._get_missing_requirements(meta)
        assert "CLI(any)" in msg
        assert "opencode" in msg


class TestAgentBrowserRequirements:
    def test_agent_browser_filtered_when_cli_missing(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b == "agent-browser" else original_which(b),
        )
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "agent-browser" not in names

    def test_agent_browser_missing_requirements_message(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b == "agent-browser" else original_which(b),
        )
        meta = loader._get_skill_meta("agent-browser")
        msg = loader._get_missing_requirements(meta)
        assert "CLI: agent-browser" in msg


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
