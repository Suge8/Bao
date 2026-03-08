from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication
QObject = QtCore.QObject


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


class _FakeRunner:
    def __init__(self) -> None:
        self.submitted = 0

    def submit(self, coro):  # type: ignore[no-untyped-def]
        self.submitted += 1
        coro.close()
        return None


MINIMAL_CONFIG = """{
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test",
      "baseUrl": "https://api.openai.com/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""


def test_load_backfills_update_defaults_for_legacy_config(tmp_path: Path) -> None:
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    assert svc.get("ui.update.enabled") is True
    assert svc.get("ui.update.autoCheck") is True
    assert svc.get("ui.update.channel") == "stable"
    assert svc.get("ui.update.feedUrl") == "https://suge8.github.io/Bao/desktop-update.json"


def test_reload_config_auto_check_is_silent_when_feed_missing() -> None:
    from app.backend.update import UpdateService

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            if dotpath == "ui.update":
                return {"enabled": True, "autoCheck": True, "channel": "stable", "feedUrl": ""}
            return default

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())
    svc.reloadConfig()

    assert svc.state == "idle"
    assert svc.errorMessage == ""
    assert runner.submitted == 0


def test_install_update_requires_available_state() -> None:
    from app.backend.update import UpdateService
    from app.backend.update_core import ReleaseAsset, ReleaseInfo

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            if dotpath == "ui.update":
                return {
                    "enabled": True,
                    "autoCheck": False,
                    "channel": "stable",
                    "feedUrl": "https://example.com/desktop-update.json",
                }
            return default

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())
    svc.reloadConfig()
    svc._release = ReleaseInfo(
        version="0.3.8",
        channel="stable",
        release_url="https://example.com/release",
        notes_url="",
        notes_markdown="",
        published_at="",
        asset=ReleaseAsset(
            platform="macos-arm64",
            url="https://example.com/Bao-0.3.8-macos-arm64-update.zip",
            kind="app-zip",
            sha256="a" * 64,
            size=123,
        ),
    )
    svc._set_state("error")

    svc.install_update()

    assert runner.submitted == 0


def test_update_bridge_signal_triggers_safe_check_path() -> None:
    from app.backend.update import UpdateBridge, UpdateService

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            if dotpath == "ui.update":
                return {
                    "enabled": True,
                    "autoCheck": False,
                    "channel": "stable",
                    "feedUrl": "https://example.com/desktop-update.json",
                }
            return default

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())
    bridge = UpdateBridge()
    _ = bridge.checkRequested.connect(svc.check_for_updates)
    svc.reloadConfig()

    bridge.checkRequested.emit()

    assert runner.submitted == 1
    assert svc.state == "checking"


def test_current_app_bundle_detects_frozen_macos_bundle_path() -> None:
    from app.backend.update import UpdateService

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            return default

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())

    with (
        patch("app.backend.update.sys.frozen", True, create=True),
        patch(
            "app.backend.update.sys.executable",
            "/Applications/Bao.app/Contents/MacOS/Bao",
            create=True,
        ),
    ):
        bundle = svc._current_app_bundle()

    assert bundle == Path("/Applications/Bao.app")


def test_config_service_load_records_runtime_diagnostic_for_invalid_config(tmp_path: Path) -> None:
    from app.backend.config import ConfigService
    from bao.runtime_diagnostics import get_runtime_diagnostics_store

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(json.dumps({"providers": []}), encoding="utf-8")
    store = get_runtime_diagnostics_store()
    store.clear()

    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    snapshot = store.snapshot(max_events=4, max_log_lines=0)

    assert snapshot["event_count"] == 1
    assert snapshot["recent_events"][0]["source"] == "config"
    assert snapshot["recent_events"][0]["code"] == "config_load_failed"


@pytest.mark.asyncio
async def test_check_async_treats_missing_feed_as_no_update_during_auto_check() -> None:
    from app.backend.update import UpdateService

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            if dotpath == "ui.update":
                return {
                    "enabled": True,
                    "autoCheck": True,
                    "channel": "stable",
                    "feedUrl": "https://example.com/desktop-update.json",
                }
            return default

    class _Response:
        status_code = 404

        def raise_for_status(self) -> None:
            raise AssertionError("raise_for_status should not be called for 404 feed")

        def json(self) -> object:
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, headers: dict[str, str]) -> _Response:
            assert url == "https://example.com/desktop-update.json"
            assert headers["Accept"] == "application/json"
            return _Response()

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())
    svc.reloadConfig()
    results: list[tuple[bool, str, object]] = []
    _ = svc._checkFinished.connect(lambda ok, err, rel: results.append((ok, err, rel)))

    with patch("app.backend.update.httpx.AsyncClient", return_value=_Client()):
        await svc._check_async()

    assert results == [(True, "", None)]


@pytest.mark.asyncio
async def test_check_async_treats_missing_feed_as_error_during_manual_check() -> None:
    from app.backend.update import UpdateService

    class _Config(QObject):
        def get(self, dotpath: str, default: object = None) -> object:
            if dotpath == "ui.update":
                return {
                    "enabled": True,
                    "autoCheck": False,
                    "channel": "stable",
                    "feedUrl": "https://example.com/desktop-update.json",
                }
            return default

    class _Response:
        status_code = 404

        def raise_for_status(self) -> None:
            raise AssertionError("raise_for_status should not be called for 404 feed")

        def json(self) -> object:
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, headers: dict[str, str]) -> _Response:
            assert url == "https://example.com/desktop-update.json"
            assert headers["Accept"] == "application/json"
            return _Response()

    runner = _FakeRunner()
    svc = UpdateService(runner, _Config())
    svc.reloadConfig()
    svc._show_check_errors = True
    results: list[tuple[bool, str, object]] = []
    _ = svc._checkFinished.connect(lambda ok, err, rel: results.append((ok, err, rel)))

    with patch("app.backend.update.httpx.AsyncClient", return_value=_Client()):
        await svc._check_async()

    assert results == [
        (False, "Update feed is not published yet (desktop-update.json returned 404).", None)
    ]
