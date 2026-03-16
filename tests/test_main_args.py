from __future__ import annotations

import importlib
import sys

pytest = importlib.import_module("pytest")
_ = pytest.importorskip("PySide6.QtGui")


def test_parse_args_supports_window_size(monkeypatch):
    from app import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "app/main.py",
            "--smoke-screenshot",
            "/tmp/demo.png",
            "--window-width",
            "640",
            "--window-height",
            "600",
        ],
    )

    parsed = main.parse_args()

    assert parsed[5] == "/tmp/demo.png"
    assert parsed[6] == 640
    assert parsed[7] == 600


def test_is_smoke_run_detects_all_smoke_entrypoints():
    from app.main import is_smoke_run

    assert is_smoke_run(True, False, None) is True
    assert is_smoke_run(False, True, None) is True
    assert is_smoke_run(False, False, "/tmp/demo.png") is True
    assert is_smoke_run(False, False, None) is False


def test_shutdown_desktop_services_calls_shutdown_before_stop():
    from app.main import shutdown_desktop_services

    events: list[str] = []

    class _Service:
        def shutdown(self) -> None:
            events.append("shutdown")

        def stop(self) -> None:
            events.append("stop")

    shutdown_desktop_services(_Service())

    assert events == ["shutdown", "stop"]
