from __future__ import annotations

from pathlib import Path

from loguru import logger

import bao.runtime_diagnostics as runtime_diagnostics


def test_configure_desktop_logging_skips_missing_console_sink(monkeypatch, tmp_path: Path) -> None:
    store = runtime_diagnostics.get_runtime_diagnostics_store()
    store.clear()

    monkeypatch.setattr(runtime_diagnostics.sys, "stderr", None)
    monkeypatch.setattr(runtime_diagnostics.sys, "__stderr__", None)

    target = tmp_path / "desktop.log"
    configured = runtime_diagnostics.configure_desktop_logging(target)
    logger.info("desktop boot ok")

    snapshot = store.snapshot(max_events=0, max_log_lines=10)

    assert configured == target
    assert snapshot["log_file_path"] == str(target)
    assert "desktop boot ok" in target.read_text(encoding="utf-8")
    assert any("desktop boot ok" in line for line in snapshot["recent_log_lines"])


def test_configure_desktop_logging_falls_back_when_data_dir_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    store = runtime_diagnostics.get_runtime_diagnostics_store()
    store.clear()

    fallback = tmp_path / "temp-logs" / "desktop.log"

    def _raise_data_dir() -> Path:
        raise OSError("home is not writable")

    monkeypatch.setattr(runtime_diagnostics, "_fallback_log_target", lambda: fallback)

    import bao.config.loader as config_loader

    monkeypatch.setattr(config_loader, "get_data_dir", _raise_data_dir)

    configured = runtime_diagnostics.configure_desktop_logging()
    logger.warning("fallback logging ok")

    snapshot = store.snapshot(max_events=4, max_log_lines=10)

    assert configured == fallback
    assert snapshot["log_file_path"] == str(fallback)
    assert snapshot["recent_events"][0]["code"] == "desktop_log_fallback"
    assert "fallback logging ok" in fallback.read_text(encoding="utf-8")
