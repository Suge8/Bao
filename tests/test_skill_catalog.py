from __future__ import annotations

from pathlib import Path

from bao.agent.skill_catalog import SkillCatalog


def _write_skill(base: Path, name: str, description: str) -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    _ = (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nmetadata: "
        "{\"bao\":{\"icon\":\"book\",\"display\":{\"name\":\"Demo Skill\",\"nameZh\":\"演示技能\"},"
        "\"capabilityRefs\":[\"filesystem\"],\"activationRefs\":[\"filesystem\"],"
        "\"examplePrompts\":[\"Do the demo thing\"]}}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_catalog_lists_user_before_builtin_and_marks_shadowed(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    user_dir = tmp_path / "user"
    _write_skill(builtin_dir, "demo", "Built-in demo")
    _write_skill(user_dir, "demo", "User demo")
    _write_skill(builtin_dir, "other", "Other built-in")

    catalog = SkillCatalog(user_skills_dir=user_dir, builtin_skills_dir=builtin_dir)
    records = catalog.list_records()

    assert [record["id"] for record in records] == [
        "user:demo",
        "builtin:demo",
        "builtin:other",
    ]
    assert records[1]["shadowed"] is True
    assert records[0]["canEdit"] is True
    assert records[0]["displayName"] == "Demo Skill"
    assert records[0]["displayNameZh"] == "演示技能"
    assert records[0]["icon"] == "book"
    assert records[0]["capabilityRefs"] == ["filesystem"]
    assert records[0]["activationRefs"] == ["filesystem"]


def test_catalog_create_update_and_delete_user_skill(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    user_dir = tmp_path / "user"
    catalog = SkillCatalog(user_skills_dir=user_dir, builtin_skills_dir=builtin_dir)

    created = catalog.create_user_skill("Design Ops", "Use for design ops tasks.")
    assert created["id"] == "user:design-ops"
    assert "Use for design ops tasks." in catalog.read_content("design-ops", "user")

    updated = catalog.update_user_skill(
        "design-ops",
        "---\nname: design-ops\ndescription: Updated\n---\n\n# design-ops\n\nUpdated body\n",
    )
    assert updated["description"] == "Updated"
    assert "Updated body" in catalog.read_content("design-ops", "user")

    catalog.delete_user_skill("design-ops")
    assert not (user_dir / "design-ops").exists()
