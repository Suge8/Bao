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
    assert (PROJECT_ROOT / "app/resources/installer/ChineseSimplified.isl").is_file()


def test_build_mac_script_includes_workspace_package_data() -> None:
    text = _read("app/scripts/build_mac.sh")

    assert '--include-data-dir="$PROJECT_ROOT/app/resources=resources"' in text
    assert "--include-package-data=bao.templates.workspace.en:*.md" in text
    assert "--include-package-data=bao.templates.workspace.zh:*.md" in text
    assert "workspace=bao/templates/workspace" not in text
    assert "--include-package=bao.templates.workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text


def test_build_win_script_includes_workspace_package_data() -> None:
    text = _read("app/scripts/build_win.bat")

    assert r'--include-data-dir="%PROJECT_ROOT%\app\resources=resources"' in text
    assert "--include-package-data=bao.templates.workspace.en:*.md" in text
    assert "--include-package-data=bao.templates.workspace.zh:*.md" in text
    assert r"workspace=bao\templates\workspace" not in text
    assert "--include-package=bao.templates.workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text


def test_package_win_installer_script_resolves_inno_setup_before_compile() -> None:
    text = _read("app/scripts/package_win_installer.bat")

    assert "resolve_inno_setup.py" in text
    assert "Resolving Inno Setup compiler" in text
    assert '"%ISCC_EXE%" /DMyAppVersion=%VERSION% app\\scripts\\bao_installer.iss' in text


def test_inno_setup_script_vendors_simplified_chinese_language_file() -> None:
    text = _read("app/scripts/bao_installer.iss")

    assert (
        'Name: "chinesesimplified"; MessagesFile: "..\\resources\\installer\\ChineseSimplified.isl"'
        in text
    )


def test_desktop_release_workflow_supports_rebuilding_existing_tag() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    assert "workflow_dispatch:" in text
    assert "release_ref:" in text
    assert "source_ref: ${{ steps.resolve.outputs.source_ref }}" in text
    assert "ref: ${{ needs.resolve-release.outputs.source_ref }}" in text
    assert "tag_name: ${{ needs.resolve-release.outputs.release_tag }}" in text
    assert "Validate desktop packaging guard rails" in text


def test_desktop_release_workflow_checks_inno_setup_before_windows_build() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    preflight_index = text.index("  preflight-windows-installer:")
    build_index = text.index("        run: app\\scripts\\build_win.bat")
    assert preflight_index < build_index
    assert "Validate Inno Setup toolchain early" in text
    assert "BAO_ISCC_EXE=$resolved" in text


def test_desktop_release_validation_job_does_not_depend_on_uv_cache() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    validate_section = text.split("  validate-version:", maxsplit=1)[1].split(
        "  build-mac:", maxsplit=1
    )[0]
    assert "uses: astral-sh/setup-uv@v4" in validate_section
    assert "enable-cache: true" not in validate_section
