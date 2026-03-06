from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (PROJECT_ROOT / rel_path).read_text(encoding="utf-8")


def test_workspace_template_directories_exist() -> None:
    assert (PROJECT_ROOT / "bao/templates/workspace").is_dir()
    assert (PROJECT_ROOT / "bao/templates/workspace/en").is_dir()
    assert (PROJECT_ROOT / "bao/templates/workspace/zh").is_dir()
    assert (PROJECT_ROOT / "bao/templates/workspace/en/INSTRUCTIONS.md").is_file()
    assert (PROJECT_ROOT / "bao/templates/workspace/en/PERSONA.md").is_file()
    assert (PROJECT_ROOT / "bao/templates/workspace/en/HEARTBEAT.md").is_file()
    assert (PROJECT_ROOT / "bao/templates/workspace/zh/INSTRUCTIONS.md").is_file()
    assert (PROJECT_ROOT / "bao/templates/workspace/zh/PERSONA.md").is_file()
    assert (PROJECT_ROOT / "bao/templates/workspace/zh/HEARTBEAT.md").is_file()


def test_build_mac_script_includes_workspace_root() -> None:
    text = _read("app/scripts/build_mac.sh")

    assert "workspace=bao/templates/workspace" in text
    assert "workspace/en=bao/templates/workspace/en" not in text
    assert "workspace/zh=bao/templates/workspace/zh" not in text


def test_build_win_script_includes_workspace_root() -> None:
    text = _read("app/scripts/build_win.bat")

    assert "workspace=bao\\templates\\workspace" in text
    assert "workspace\\en=bao\\templates\\workspace\\en" not in text
    assert "workspace\\zh=bao\\templates\\workspace\\zh" not in text
