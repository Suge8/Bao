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
    assert "--include-package=bao.templates.workspace" not in text
    assert "workspace=bao/templates/workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text
    assert "imageformats/libqpdf.dylib" in text


def test_build_mac_pyinstaller_script_includes_desktop_resources() -> None:
    text = _read("app/scripts/build_mac_pyinstaller.sh")

    assert "uv sync --extra desktop-build-pyinstaller" in _read("app/README.md")
    assert '--add-data "$PROJECT_ROOT/app/qml:app/qml"' in text
    assert '--add-data "$PROJECT_ROOT/app/resources:app/resources"' in text
    assert '--add-data "$PROJECT_ROOT/assets:assets"' in text
    assert '--add-data "$PROJECT_ROOT/bao/skills:bao/skills"' in text
    assert '--add-data "$PROJECT_ROOT/bao/templates/workspace:bao/templates/workspace"' in text
    assert "--collect-submodules bao.channels" in text
    assert "--collect-submodules bao.providers" in text
    assert 'plist_set_or_add "$INFO_PLIST" "CFBundleShortVersionString" "$VERSION"' in text
    assert 'plist_set_or_add "$INFO_PLIST" "CFBundleVersion" "$VERSION"' in text


def test_build_win_pyinstaller_script_includes_desktop_resources() -> None:
    text = _read("app/scripts/build_win_pyinstaller.bat")

    assert '--add-data "%PROJECT_ROOT%\\app\\qml;app\\qml"' in text
    assert '--add-data "%PROJECT_ROOT%\\app\\resources;app\\resources"' in text
    assert '--add-data "%PROJECT_ROOT%\\assets;assets"' in text
    assert (
        '--add-data "%PROJECT_ROOT%\\bao\\templates\\workspace;bao\\templates\\workspace"' in text
    )
    assert "--collect-submodules bao.channels" in text
    assert "--collect-submodules bao.providers" in text


def test_build_win_script_includes_workspace_package_data() -> None:
    text = _read("app/scripts/build_win.bat")

    assert r'--include-data-dir="%PROJECT_ROOT%\app\resources=resources"' in text
    assert "--include-package-data=bao.templates.workspace.en:*.md" in text
    assert "--include-package-data=bao.templates.workspace.zh:*.md" in text
    assert "--include-package=bao.templates.workspace" not in text
    assert r"workspace=bao\templates\workspace" not in text
    assert "--noinclude-qt-plugins=tls" in text


def test_bundled_desktop_font_exists() -> None:
    assert (PROJECT_ROOT / "app/resources/fonts/OPPO Sans.ttf").is_file()


def test_bundled_windows_icon_exists() -> None:
    assert (PROJECT_ROOT / "app/resources/logo.ico").is_file()


def test_app_readme_documents_bundled_font_strategy() -> None:
    text = _read("app/README.md")

    assert "app/resources/fonts/OPPO Sans.ttf" in text
    assert "只保留应用级这一处字体决策" in text
    assert "`app/main.py`" in text


def test_app_readme_documents_single_windows_icon_source() -> None:
    text = _read("app/README.md")

    assert "app/resources/logo.ico" in text
    assert "logo-circle.png" in text


def test_package_win_installer_script_resolves_inno_setup_before_compile() -> None:
    text = _read("app/scripts/package_win_installer.bat")

    assert "resolve_inno_setup.py" in text
    assert "Resolving Inno Setup compiler" in text
    assert "where uv >nul 2>nul" in text
    assert "Missing value for --build-root" in text
    assert 'if not exist "%BUILD_ROOT%\\Bao.exe" (' in text
    assert "if errorlevel 1 (" in text
    assert (
        '"%ISCC_EXE%" /DMyAppVersion=%VERSION% "/DBuildSource=%BUILD_ROOT%" app\\scripts\\bao_installer.iss'
        in text
    )


def test_mac_packaging_scripts_accept_explicit_app_path() -> None:
    dmg = _read("app/scripts/create_dmg.sh")
    update_zip = _read("app/scripts/create_update_zip.sh")

    assert "--app-path" in dmg
    assert "--app-path" in update_zip


def test_mac_packaging_scripts_prefer_pyinstaller_output_by_default() -> None:
    dmg = _read("app/scripts/create_dmg.sh")
    update_zip = _read("app/scripts/create_update_zip.sh")

    assert 'PYINSTALLER_APP_PATH="$PROJECT_ROOT/dist-pyinstaller/dist/$APP_NAME.app"' in dmg
    assert 'NUITKA_APP_PATH="$PROJECT_ROOT/dist/$APP_NAME.app"' in dmg
    assert 'if [[ -d "$PYINSTALLER_APP_PATH" ]]; then' in dmg
    assert 'APP_PATH="$PYINSTALLER_APP_PATH"' in dmg
    assert 'APP_PATH="$NUITKA_APP_PATH"' in dmg
    assert 'PYINSTALLER_APP_PATH="$PROJECT_ROOT/dist-pyinstaller/dist/$APP_NAME.app"' in update_zip
    assert 'NUITKA_APP_PATH="$PROJECT_ROOT/dist/$APP_NAME.app"' in update_zip


def test_windows_installer_prefers_pyinstaller_output_by_default() -> None:
    text = _read("app/scripts/package_win_installer.bat")

    assert 'set "PYINSTALLER_BUILD_ROOT=%PROJECT_ROOT%\\dist-pyinstaller\\dist\\Bao"' in text
    assert 'set "NUITKA_BUILD_ROOT=%PROJECT_ROOT%\\dist\\build-win-x64\\main.dist"' in text
    assert 'if exist "%PYINSTALLER_BUILD_ROOT%\\Bao.exe" (' in text
    assert 'set "BUILD_ROOT=%PYINSTALLER_BUILD_ROOT%"' in text
    assert 'set "BUILD_ROOT=%NUITKA_BUILD_ROOT%"' in text
    assert 'set "REQUIRE_PRIMARY=0"' in text
    assert 'if /I "%~1"=="--require-primary" (' in text
    assert 'if /I "%BAO_DESKTOP_REQUIRE_PRIMARY%"=="1" (' in text


def test_inno_setup_script_vendors_simplified_chinese_language_file() -> None:
    text = _read("app/scripts/bao_installer.iss")

    assert (
        'Name: "chinesesimplified"; MessagesFile: "..\\resources\\installer\\ChineseSimplified.isl"'
        in text
    )


def test_vendored_chinese_language_file_covers_previous_missing_keys() -> None:
    text = _read("app/resources/installer/ChineseSimplified.isl")

    assert "AbortRetryIgnoreCancel=" in text
    assert "ArchiveIncorrectPassword=" in text
    assert "ButtonStopDownload=" in text
    assert "ChangeDiskTitle=" in text
    assert "ConfirmDeleteSharedFileTitle=" in text
    assert "DownloadingLabel2=" in text
    assert "ErrorCopying=" in text
    assert "ExtractingLabel=" in text
    assert "PathLabel=" in text
    assert "VerificationSignatureInvalid=" in text


def test_windows_icon_pipeline_uses_single_bundled_ico() -> None:
    build_win = _read("app/scripts/build_win.bat")
    installer = _read("app/scripts/bao_installer.iss")
    app_readme = _read("app/README.md")
    main_py = _read("app/main.py")

    assert r'--windows-icon-from-ico="%PROJECT_ROOT%\app\resources\logo.ico"' in build_win
    assert r"SetupIconFile=..\resources\logo.ico" in installer
    assert "app/resources/logo.ico" in app_readme
    assert "WINDOWS_APP_ICON_RELATIVE_PATHS" in main_py


def test_desktop_release_workflow_supports_rebuilding_existing_tag() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    assert "workflow_dispatch:" in text
    assert "release_ref:" in text
    assert "source_ref: ${{ steps.resolve.outputs.source_ref }}" in text
    assert "ref: ${{ needs.resolve-release.outputs.source_ref }}" in text
    assert "tag_name: ${{ needs.resolve-release.outputs.release_tag }}" in text
    assert "Validate desktop packaging guard rails" in text


def test_desktop_release_workflow_uses_pyinstaller_as_primary_packager() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    build_mac_section = text.split("  build-mac:", maxsplit=1)[1].split(
        "  preflight-windows-installer:", maxsplit=1
    )[0]
    assert "desktop-build-pyinstaller" in build_mac_section
    assert "build_mac_pyinstaller.sh" in build_mac_section
    assert "create_dmg.sh --arch ${{ matrix.arch }} --app-path" in build_mac_section
    assert "create_update_zip.sh --arch ${{ matrix.arch }} --app-path" in build_mac_section
    assert "ccache" not in build_mac_section
    assert "nuitka" not in build_mac_section.lower()


def test_desktop_release_workflow_checks_inno_setup_before_windows_build() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    preflight_index = text.index("  preflight-windows-installer:")
    build_index = text.index("        run: app\\scripts\\build_win_pyinstaller.bat")
    assert preflight_index < build_index
    assert "Validate Inno Setup toolchain early" in text
    assert "BAO_ISCC_EXE=$resolved" in text
    assert "choco install innosetup --version=${{ env.INNOSETUP_VERSION }} -y" in text
    assert "BAO_DESKTOP_REQUIRE_PRIMARY: '1'" in text
    assert (
        "package_win_installer.bat --require-primary --build-root dist-pyinstaller\\dist\\Bao"
        in text
    )


def test_desktop_ci_lite_uses_pyinstaller_build_dependencies() -> None:
    text = _read(".github/workflows/desktop-ci-lite.yml")

    assert "desktop-build-pyinstaller" in text
    assert "build_mac_pyinstaller.sh" in text
    assert "build_win_pyinstaller.bat" in text
    assert "Ensure Inno Setup" in text
    assert "Create installer smoke artifact" in text
    assert "Validate installer artifact exists" in text
    assert "choco install innosetup --version=${{ env.INNOSETUP_VERSION }} -y" in text


def test_app_readme_declares_pyinstaller_primary_and_nuitka_backup() -> None:
    text = _read("app/README.md")

    assert "当前默认打包路径已切到 **PyInstaller onedir**；`Nuitka` 保留为备用方案。" in text


def test_app_readme_documents_pyinstaller_default_scripts() -> None:
    text = _read("app/README.md")

    assert "build_mac_pyinstaller.sh" in text
    assert "build_win_pyinstaller.bat" in text
    assert "# macOS 默认构建（PyInstaller）" in text
    assert "# Windows 默认构建（PyInstaller）" in text
    assert "# macOS 备用构建（Nuitka）" in text
    assert "# Windows 备用构建（Nuitka）" in text


def test_desktop_release_validation_job_does_not_depend_on_uv_cache() -> None:
    text = _read(".github/workflows/desktop-release.yml")

    validate_section = text.split("  validate-version:", maxsplit=1)[1].split(
        "  build-mac:", maxsplit=1
    )[0]
    assert "uses: astral-sh/setup-uv@v4" in validate_section
    assert "enable-cache: true" not in validate_section
