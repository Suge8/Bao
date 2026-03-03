"""Tests for ConfigService."""

from __future__ import annotations

import importlib
import json
import sys
from unittest.mock import patch

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QCoreApplication = QtCore.QCoreApplication


# Ensure a QCoreApplication exists for QObject tests
@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


MINIMAL_CONFIG = """{
  // provider config
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test",
      "baseUrl": "https://api.openai.com/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o",
      "temperature": 0.7,
      "maxTokens": 4096
    }
  }
}"""


def test_load_missing_file(tmp_path):
    from app.backend.config import ConfigService

    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=tmp_path / "missing.jsonc"):
        svc.load()
    assert svc.isValid is False


def test_load_valid_config(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    assert svc.isValid is True


def test_get_value_after_load(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    assert svc.get("agents.defaults.model") == "openai/gpt-4o"
    assert svc.get("providers.openaiCompatible.apiKey") == "sk-test"
    assert svc.get("nonexistent.path", "fallback") == "fallback"


def test_get_value_slot(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    assert svc.getValue("agents.defaults.temperature") == 0.7


def test_save_patches_value(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    ok = svc.save({"agents.defaults.model": "anthropic/claude-3-5-sonnet"})
    assert ok is True
    written = cfg.read_text(encoding="utf-8")
    assert "// provider config" in written
    data = json.loads(_strip_comments(written))
    assert data["agents"]["defaults"]["model"] == "anthropic/claude-3-5-sonnet"


def test_save_reasoning_effort_off(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save({"agents.defaults.reasoningEffort": "off"})
    assert ok is True

    written = cfg.read_text(encoding="utf-8")
    data = json.loads(_strip_comments(written))
    assert data["agents"]["defaults"]["reasoningEffort"] == "off"


def test_save_after_missing_load_marks_valid(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    assert svc.isValid is False

    ok = svc.save({"ui": {"language": "zh"}})
    assert ok is True
    assert svc.isValid is True


def test_save_reports_patch_exception(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    errors = []
    svc.saveError.connect(errors.append)
    with patch("app.backend.config.patch_jsonc", side_effect=ValueError("boom")):
        ok = svc.save({"ui": {"language": "zh"}})

    assert ok is False
    assert any("Patch failed" in e for e in errors)


def test_save_before_load_fails():
    from app.backend.config import ConfigService

    svc = ConfigService()
    ok = svc.save({"agents.defaults.model": "x"})
    assert ok is False


def test_save_channel_enabled_without_token_fails(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    errors = []
    svc.saveError.connect(errors.append)
    ok = svc.save({"channels.telegram.enabled": True})
    assert ok is False
    assert any("telegram" in e.lower() for e in errors)


def test_save_channel_enabled_with_token_succeeds(tmp_path):
    from app.backend.config import ConfigService

    # Config must already have the channels key for patch to work
    config_with_channels = (
        MINIMAL_CONFIG.rstrip("}")
        + ',\n  "channels": {\n    "telegram": {\n      "enabled": false,\n      "token": ""\n    }\n  }\n}'
    )
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_with_channels, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    ok = svc.save(
        {
            "channels.telegram.enabled": True,
            "channels.telegram.token": "bot123:TOKEN",
        }
    )
    assert ok is True


def test_save_rejects_invalid_bool_value(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    config_with_mochat = (
        MINIMAL_CONFIG.rstrip("}")
        + ',\n  "channels": {\n    "mochat": {\n      "enabled": false,\n      "socketDisableMsgpack": false\n    }\n  }\n}'
    )
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_with_mochat, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()
    errors = []
    svc.saveError.connect(errors.append)
    ok = svc.save({"channels.mochat.socketDisableMsgpack": "11"})
    assert ok is False
    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["channels"]["mochat"]["socketDisableMsgpack"] is False
    assert any("Config validation failed" in e for e in errors)
