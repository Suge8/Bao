from __future__ import annotations

from pathlib import Path

import pytest

from app.scripts.build_qml_rcc import _qt_tool_path, build_qrc_text


def test_build_qrc_text_excludes_output_rcc_from_resources(tmp_path: Path) -> None:
    qml_root = tmp_path / "qml"
    resources_root = tmp_path / "resources"
    cache_root = tmp_path / "cache"
    output_rcc = resources_root / "desktop_qml.rcc"

    qml_root.mkdir(parents=True)
    resources_root.mkdir(parents=True)
    cache_root.mkdir(parents=True)

    (qml_root / "Main.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
    (resources_root / "logo.svg").write_text("<svg />\n", encoding="utf-8")
    output_rcc.write_bytes(b"old-rcc")

    qrc_text = build_qrc_text(
        qml_root,
        resources_root,
        cache_root=cache_root,
        with_qml_cache=False,
        skip_resource_paths={output_rcc},
    )

    assert "logo.svg" in qrc_text
    assert "desktop_qml.rcc" not in qrc_text


def test_qt_tool_path_falls_back_to_pyside_wrappers_in_scripts_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_venv = tmp_path / "venv"
    fake_scripts = fake_venv / "Scripts"
    fake_pyside = fake_venv / "Lib" / "site-packages" / "PySide6"
    fake_wrapper = fake_scripts / "pyside6-rcc.exe"
    fake_wrapper.parent.mkdir(parents=True)
    fake_pyside.mkdir(parents=True)
    fake_wrapper.write_text("", encoding="utf-8")

    monkeypatch.setattr("app.scripts.build_qml_rcc.PySide6.__file__", str(fake_pyside / "__init__.py"))
    monkeypatch.setattr("app.scripts.build_qml_rcc.sys.executable", str(fake_venv / "python.exe"))
    monkeypatch.setattr("app.scripts.build_qml_rcc.sysconfig.get_path", lambda name: str(fake_scripts))

    assert _qt_tool_path("rcc") == fake_wrapper
