from __future__ import annotations

import importlib
from pathlib import Path

pytest = importlib.import_module("pytest")
_ = pytest.importorskip("PySide6.QtGui")


def _main_module():
    return importlib.import_module("app.main")


def test_resolve_qml_path_prefers_pyinstaller_meipass_layout(monkeypatch, tmp_path: Path) -> None:
    main = _main_module()

    source_root = tmp_path / "src" / "app"
    source_root.mkdir(parents=True)
    fake_file = source_root / "main.py"
    fake_file.write_text("", encoding="utf-8")

    meipass = tmp_path / "bundle"
    qml_path = meipass / "app" / "qml" / "Main.qml"
    qml_path.parent.mkdir(parents=True)
    qml_path.write_text("import QtQuick\nItem {}\n", encoding="utf-8")

    exe_path = tmp_path / "dist" / "Bao" / "Bao.exe"
    exe_path.parent.mkdir(parents=True)
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(main, "__file__", str(fake_file))
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(main.sys, "executable", str(exe_path), raising=False)

    assert main.resolve_qml_path(None) == qml_path.resolve()


def test_resolve_app_resource_path_supports_pyinstaller_windows_layout(
    monkeypatch, tmp_path: Path
) -> None:
    main = _main_module()

    source_root = tmp_path / "src" / "app"
    source_root.mkdir(parents=True)
    fake_file = source_root / "main.py"
    fake_file.write_text("", encoding="utf-8")

    exe_dir = tmp_path / "dist" / "Bao"
    exe_path = exe_dir / "Bao.exe"
    exe_dir.mkdir(parents=True)
    exe_path.write_text("", encoding="utf-8")

    icon_path = exe_dir / "resources" / "logo.ico"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"ico")

    monkeypatch.setattr(main, "__file__", str(fake_file))
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "_MEIPASS", "", raising=False)
    monkeypatch.setattr(main.sys, "executable", str(exe_path), raising=False)
    monkeypatch.setattr(main.sys, "platform", "win32", raising=False)

    assert main.resolve_app_icon_path() == icon_path.resolve()


def test_resolve_app_resource_path_supports_pyinstaller_macos_resources_layout(
    monkeypatch, tmp_path: Path
) -> None:
    main = _main_module()

    source_root = tmp_path / "src" / "app"
    source_root.mkdir(parents=True)
    fake_file = source_root / "main.py"
    fake_file.write_text("", encoding="utf-8")

    app_bundle = tmp_path / "Bao.app"
    exe_path = app_bundle / "Contents" / "MacOS" / "Bao"
    exe_path.parent.mkdir(parents=True)
    exe_path.write_text("", encoding="utf-8")

    font_path = (
        app_bundle / "Contents" / "Resources" / "app" / "resources" / "fonts" / "OPPO Sans.ttf"
    )
    font_path.parent.mkdir(parents=True)
    font_path.write_bytes(b"font")

    monkeypatch.setattr(main, "__file__", str(fake_file))
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "_MEIPASS", "", raising=False)
    monkeypatch.setattr(main.sys, "executable", str(exe_path), raising=False)

    assert main.resolve_bundled_app_font_path() == font_path.resolve()
