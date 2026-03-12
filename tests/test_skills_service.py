from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from app.backend.asyncio_runner import AsyncioRunner

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.gui]

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


@pytest.fixture()
def runner() -> Iterator[AsyncioRunner]:
    current = AsyncioRunner()
    current.start()
    try:
        yield current
    finally:
        current.shutdown()


def test_skills_service_create_save_delete_and_filter(
    tmp_path: Path, runner: AsyncioRunner
) -> None:
    from app.backend.skills import SkillsService

    service = SkillsService(runner, str(tmp_path))

    created_events: list[tuple[str, bool]] = []
    _ = service.operationFinished.connect(lambda message, ok: created_events.append((message, ok)))

    assert service.createSkill("my-ui-skill", "Use for premium UI polish.") is True
    assert cast(str, cast(object, service.selectedSkillId)) == "workspace:my-ui-skill"
    assert cast(int, cast(object, service.workspaceCount)) >= 1
    assert created_events[-1] == ("created", True)

    assert (
        service.saveSelectedContent(
            "---\nname: my-ui-skill\ndescription: Updated UI workflow\n---\n\n# my-ui-skill\n\nBody\n"
        )
        is True
    )
    selected_skill = cast(dict[str, object], cast(object, service.selectedSkill))
    assert selected_skill["description"] == "Updated UI workflow"
    assert created_events[-1] == ("saved", True)

    service.setSourceFilter("workspace")
    workspace_items = cast(list[dict[str, object]], cast(object, service.skills))
    assert all(item["source"] == "workspace" for item in workspace_items)

    service.setQuery("updated ui")
    filtered_items = cast(list[dict[str, object]], cast(object, service.skills))
    assert len(filtered_items) == 1
    assert filtered_items[0]["name"] == "my-ui-skill"

    service.setQuery("")
    service.setSourceFilter("all")
    assert service.deleteSelectedSkill() is True
    assert created_events[-1] == ("deleted", True)
    assert not (tmp_path / "skills" / "my-ui-skill").exists()


def test_skills_service_can_fork_builtin_skill(tmp_path: Path, runner: AsyncioRunner) -> None:
    from app.backend.skills import SkillsService

    service = SkillsService(runner, str(tmp_path))
    builtin_skills = cast(list[dict[str, object]], cast(object, service.skills))
    builtin = next(item for item in builtin_skills if item["source"] == "builtin")

    service.selectSkill(str(builtin["id"]))
    assert service.forkSelectedSkill() is True
    selected_skill = cast(dict[str, object], cast(object, service.selectedSkill))
    assert selected_skill["source"] == "workspace"
    assert (tmp_path / "skills" / str(builtin["name"]) / "SKILL.md").exists()


def test_parse_search_output_extracts_skill_refs() -> None:
    from app.backend.skills import SkillsService

    output = """
Install with npx skills add vercel-labs/agent-skills@frontend-design
vercel-labs/agent-skills@frontend-design
Install with npx skills add acme/skills@docs-pro
"""
    parsed = SkillsService.parse_search_output(output)

    assert [item["reference"] for item in parsed] == [
        "vercel-labs/agent-skills@frontend-design",
        "acme/skills@docs-pro",
    ]
    assert parsed[0]["name"] == "frontend-design"


def test_import_installed_skills_copies_into_workspace(
    tmp_path: Path, runner: AsyncioRunner
) -> None:
    from app.backend.skills import SkillsService

    service = SkillsService(runner, str(tmp_path))
    source_root = tmp_path / "temp" / ".agents" / "skills" / "design-ops"
    source_root.mkdir(parents=True)
    (source_root / "SKILL.md").write_text(
        "---\nname: design-ops\ndescription: Design ops\n---\n\n# design-ops\n",
        encoding="utf-8",
    )

    imported_ids = service._import_installed_skills(tmp_path / "temp" / ".agents" / "skills")

    assert imported_ids == ["workspace:design-ops"]
    assert (tmp_path / "skills" / "design-ops" / "SKILL.md").exists()


def test_import_installed_skills_can_filter_target_names(
    tmp_path: Path, runner: AsyncioRunner
) -> None:
    from app.backend.skills import SkillsService

    service = SkillsService(runner, str(tmp_path))
    for skill_name in ("design-ops", "frontend-design"):
        source_dir = tmp_path / ".agents" / "skills" / skill_name
        source_dir.mkdir(parents=True)
        (source_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: {skill_name}\n---\n\n# {skill_name}\n",
            encoding="utf-8",
        )

    imported_ids = service._import_installed_skills(
        tmp_path / ".agents" / "skills", target_names=["frontend-design"]
    )

    assert imported_ids == ["workspace:frontend-design"]
    assert not (tmp_path / "skills" / "design-ops").exists()
    assert (tmp_path / "skills" / "frontend-design" / "SKILL.md").exists()


def test_extract_reference_name_returns_skill_suffix() -> None:
    from app.backend.skills import SkillsService

    assert (
        SkillsService._extract_reference_name("vercel-labs/agent-skills@frontend-design")
        == "frontend-design"
    )
