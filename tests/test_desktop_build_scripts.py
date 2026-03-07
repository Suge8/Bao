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


def test_build_mac_script_includes_workspace_package_data() -> None:
    text = _read("app/scripts/build_mac.sh")

    assert "--include-package=bao.templates.workspace" in text
    assert "--include-package=bao.templates.workspace.en" in text
    assert "--include-package=bao.templates.workspace.zh" in text
    assert "--include-package-data=bao.templates.workspace.en:*.md" in text
    assert "--include-package-data=bao.templates.workspace.zh:*.md" in text
    assert "workspace=bao/templates/workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text


def test_build_win_script_includes_workspace_package_data() -> None:
    text = _read("app/scripts/build_win.bat")

    assert "--include-package=bao.templates.workspace" in text
    assert "--include-package=bao.templates.workspace.en" in text
    assert "--include-package=bao.templates.workspace.zh" in text
    assert "--include-package-data=bao.templates.workspace.en:*.md" in text
    assert "--include-package-data=bao.templates.workspace.zh:*.md" in text
    assert "workspace=bao\\templates\\workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text


def test_package_win_installer_script_resolves_inno_setup_before_compile() -> None:
    text = _read("app/scripts/package_win_installer.bat")

    assert "resolve_inno_setup.py" in text
    assert "Resolving Inno Setup compiler" in text
    assert '"%ISCC_EXE%" /DMyAppVersion=%VERSION% app\\scripts\\bao_installer.iss' in text
