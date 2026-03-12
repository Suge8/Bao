from __future__ import annotations

from pathlib import Path

from bao.agent.skill_catalog import SkillCatalog


def _write_skill(base: Path, name: str, description: str) -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _ = (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_catalog_lists_workspace_before_builtin_and_marks_shadowed(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    workspace = tmp_path / "workspace"
    _write_skill(builtin_dir, "demo", "Built-in demo")
    _write_skill(workspace / "skills", "demo", "Workspace demo")
    _write_skill(builtin_dir, "other", "Other built-in")

    catalog = SkillCatalog(workspace=workspace, builtin_skills_dir=builtin_dir)
    records = catalog.list_records()

    assert [record["id"] for record in records] == [
        "workspace:demo",
        "builtin:demo",
        "builtin:other",
    ]
    assert records[1]["shadowed"] is True
    assert records[0]["canEdit"] is True
    assert records[1]["canFork"] is True


def test_catalog_create_update_and_delete_workspace_skill(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    catalog = SkillCatalog(workspace=workspace, builtin_skills_dir=builtin_dir)

    created = catalog.create_workspace_skill("Design Ops", "Use for design ops tasks.")
    assert created["id"] == "workspace:design-ops"
    assert "Use for design ops tasks." in catalog.read_content("design-ops", "workspace")

    updated = catalog.update_workspace_skill(
        "design-ops",
        "---\nname: design-ops\ndescription: Updated\n---\n\n# design-ops\n\nUpdated body\n",
    )
    assert updated["description"] == "Updated"
    assert "Updated body" in catalog.read_content("design-ops", "workspace")

    catalog.delete_workspace_skill("design-ops")
    assert not (workspace / "skills" / "design-ops").exists()


def test_catalog_forks_builtin_skill_into_workspace(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    workspace = tmp_path / "workspace"
    _write_skill(builtin_dir, "copy-me", "Built-in source")

    catalog = SkillCatalog(workspace=workspace, builtin_skills_dir=builtin_dir)
    forked = catalog.fork_builtin_skill("copy-me")

    assert forked["id"] == "workspace:copy-me"
    assert (workspace / "skills" / "copy-me" / "SKILL.md").exists()
    assert "Built-in source" in catalog.read_content("copy-me", "workspace")
