# ruff: noqa: F403, F405
from __future__ import annotations

from tests._coding_agent_skill_testkit import *


class TestBinsAnyRequirements:
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
    def test_agent_browser_not_filtered_when_cli_missing(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b == "agent-browser" else original_which(b),
        )
        skills = loader.list_skills(filter_unavailable=True)
        names = [s["name"] for s in skills]
        assert "agent-browser" in names

    def test_agent_browser_missing_requirements_message_is_empty(self, tmp_path, monkeypatch):
        loader = SkillsLoader(workspace=tmp_path, builtin_skills_dir=SKILL_DIR)
        original_which = __import__("shutil").which
        monkeypatch.setattr(
            "shutil.which",
            lambda b: None if b == "agent-browser" else original_which(b),
        )
        meta = loader._get_skill_meta("agent-browser")
        msg = loader._get_missing_requirements(meta)
        assert msg == ""
