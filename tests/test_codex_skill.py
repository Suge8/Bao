import json
from pathlib import Path

from bao.agent.skills import SkillsLoader

SKILL_DIR = Path(__file__).parent.parent / "bao" / "skills"
CODEX_SKILL_DIR = SKILL_DIR / "codex"


def test_codex_skill_directory_exists() -> None:
    assert CODEX_SKILL_DIR.is_dir()


def test_codex_skill_md_exists() -> None:
    assert (CODEX_SKILL_DIR / "SKILL.md").is_file()


def test_codex_skill_discovered_by_loader(tmp_path: Path) -> None:
    loader = SkillsLoader(
        workspace=tmp_path,
        builtin_skills_dir=SKILL_DIR,
    )
    skills = loader.list_skills(filter_unavailable=False)
    names = [s["name"] for s in skills]
    assert "codex" in names


def test_codex_skill_has_requires_bin(tmp_path: Path) -> None:
    loader = SkillsLoader(
        workspace=tmp_path,
        builtin_skills_dir=SKILL_DIR,
    )
    meta = loader.get_skill_metadata("codex")
    assert meta is not None
    raw = meta.get("metadata", "")
    parsed = json.loads(raw) if isinstance(raw, str) and raw else {}
    requires = parsed.get("bao", {}).get("requires", {})
    assert "codex" in requires.get("bins", [])
