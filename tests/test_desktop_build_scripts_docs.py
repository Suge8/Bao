# ruff: noqa: F403, F405
from __future__ import annotations

from tests._desktop_build_scripts_testkit import *


def test_app_readme_documents_mac_imessage_permissions() -> None:
    text = _read("app/README.md")

    assert "NSAppleEventsUsageDescription" in text
    assert "Full Disk Access" in text
    assert "Messages" in text


def test_desktop_packaging_doc_covers_mac_imessage_permissions() -> None:
    text = _read("app/DESKTOP_PACKAGING.md")

    assert "NSAppleEventsUsageDescription" in text
    assert "Full Disk Access" in text
    assert "Privacy & Security > Automation" in text
    assert "update_agent_browser_runtime.py" in text
    assert "verify_browser_runtime.py" in text
    assert "sync_browser_runtime.py" in text


def test_app_readme_documents_bundled_font_strategy() -> None:
    text = _read("app/README.md")

    assert "app/resources/fonts/OPPO Sans.ttf" in text
    assert "只保留应用级这一处字体决策" in text
    assert "`app/main.py`" in text


def test_app_readme_documents_single_windows_icon_source() -> None:
    text = _read("app/README.md")

    assert "app/resources/logo.ico" in text
    assert "logo-circle.png" in text


def test_app_readme_documents_unified_installer_brand_assets() -> None:
    text = _read("app/README.md")

    assert "generate_installer_assets.py" in text
    assert "dmg-background.png" in text
    assert "windowContentInsetTop/Side/Bottom" in text


def test_app_readme_documents_shared_installer_brand_source() -> None:
    text = _read("app/README.md")

    assert "generate_installer_assets.py" in text
    assert "dmg-background.png" in text
    assert "避免 Win/mac 安装体验与桌面端首屏漂移" in text


def test_installer_asset_generator_is_single_source_for_windows_and_dmg() -> None:
    text = _read("app/scripts/generate_installer_assets.py")

    assert "def build_dmg_background" in text
    assert 'default="app/resources/dmg-background.png"' in text
    assert "Generate unified Windows installer and macOS DMG brand assets" in text


def test_app_readme_declares_pyinstaller_primary_and_nuitka_backup() -> None:
    text = _read("app/README.md")

    assert "PyInstaller" in text
    assert "Nuitka" in text
    assert "primary" in text.lower()


def test_app_readme_documents_pyinstaller_default_scripts() -> None:
    text = _read("app/README.md")

    assert "build_mac_pyinstaller.sh" in text
    assert "build_win_pyinstaller.bat" in text
