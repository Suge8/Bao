from __future__ import annotations

import shutil
from pathlib import Path

from bao.agent.skill_catalog import SkillCatalog
from bao.agent.skill_registry import build_skill_workspace_snapshot


def _write_skill(base: Path, name: str, description: str, metadata: str) -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _ = (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nmetadata: {metadata}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_skill_workspace_snapshot_groups_statuses_and_shadowed(monkeypatch, tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    workspace = tmp_path / "workspace"
    _write_skill(
        builtin_dir,
        "ready-skill",
        "Uses filesystem.",
        '{"bao":{"icon":"book","display":{"name":"Ready Skill","nameZh":"就绪技能"},"capabilityRefs":["filesystem"],"activationRefs":["filesystem"]}}',
    )
    _write_skill(
        builtin_dir,
        "setup-skill",
        "Needs coding backend.",
        '{"bao":{"icon":"computer","display":{"name":"Setup Skill","nameZh":"待设置技能"},"capabilityRefs":["coding"],"activationRefs":["coding"]}}',
    )
    _write_skill(
        builtin_dir,
        "instruction-skill",
        "Pure guidance.",
        '{"bao":{"icon":"message","display":{"name":"Instruction Skill","nameZh":"指导技能"}}}',
    )
    _write_skill(
        builtin_dir,
        "shadowed-skill",
        "Built-in shadowed skill.",
        '{"bao":{"icon":"toolbox","display":{"name":"Shadowed Skill","nameZh":"被覆盖技能"},"capabilityRefs":["filesystem"],"activationRefs":["filesystem"]}}',
    )
    _write_skill(
        workspace / "skills",
        "shadowed-skill",
        "Workspace shadowing skill.",
        '{"bao":{"icon":"toolbox","display":{"name":"Workspace Shadow","nameZh":"工作区覆盖"},"capabilityRefs":["filesystem"],"activationRefs":["filesystem"]}}',
    )

    original_which = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda name: None if name in {"opencode", "codex", "claude"} else original_which(name),
    )

    snapshot = build_skill_workspace_snapshot(
        catalog=SkillCatalog(workspace=workspace, builtin_skills_dir=builtin_dir),
        config_data={},
        query="",
        source_filter="all",
        selected_id="",
    )

    items = list(snapshot.items)
    by_id = {str(item["id"]): item for item in items}
    assert by_id["builtin:ready-skill"]["status"] == "ready"
    assert by_id["builtin:setup-skill"]["status"] == "needs_setup"
    assert by_id["builtin:instruction-skill"]["status"] == "instruction_only"
    assert by_id["workspace:shadowed-skill"]["source"] == "workspace"
    shadowed_builtin = next(item for item in items if item["id"] == "builtin:shadowed-skill")
    assert shadowed_builtin["sectionKey"] == "shadowed"
    assert snapshot.overview["shadowedCount"] == 1
    assert snapshot.overview["readyCount"] >= 2


def test_skill_workspace_snapshot_filters_by_ready_state(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    workspace = tmp_path / "workspace"
    _write_skill(
        builtin_dir,
        "ready-skill",
        "Uses filesystem.",
        '{"bao":{"icon":"book","display":{"name":"Ready Skill","nameZh":"就绪技能"},"capabilityRefs":["filesystem"],"activationRefs":["filesystem"]}}',
    )
    _write_skill(
        builtin_dir,
        "instruction-skill",
        "Pure guidance.",
        '{"bao":{"icon":"message","display":{"name":"Instruction Skill","nameZh":"指导技能"}}}',
    )

    snapshot = build_skill_workspace_snapshot(
        catalog=SkillCatalog(workspace=workspace, builtin_skills_dir=builtin_dir),
        config_data={},
        query="",
        source_filter="ready",
        selected_id="",
    )

    items = list(snapshot.items)
    assert [item["name"] for item in items] == ["ready-skill"]
    assert snapshot.selected_id == "builtin:ready-skill"
