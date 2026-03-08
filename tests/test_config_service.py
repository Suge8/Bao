"""Tests for ConfigService."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QGuiApplication = QtGui.QGuiApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
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

    cfg = tmp_path / "config.jsonc"

    def _bootstrap() -> bool:
        cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
        return True

    svc = ConfigService()
    with (
        patch("bao.config.loader.get_config_path", return_value=cfg),
        patch("bao.config.loader.ensure_first_run", side_effect=_bootstrap) as bootstrap,
    ):
        svc.load()

    bootstrap.assert_called_once()
    assert svc.isValid is True
    assert cfg.exists()


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


def test_get_config_file_path_after_load(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    assert svc.getConfigFilePath() == str(cfg)


def test_open_config_directory_uses_parent_folder(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    with patch("app.backend.config.QDesktopServices.openUrl") as open_url:
        svc.openConfigDirectory()

    open_url.assert_called_once()
    url = open_url.call_args.args[0]
    assert url.isLocalFile()
    assert Path(url.toLocalFile()) == cfg.parent


def test_export_data_returns_detached_snapshot(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    snapshot = svc.exportData()
    agents = snapshot["agents"]
    assert isinstance(agents, dict)
    defaults = agents["defaults"]
    assert isinstance(defaults, dict)
    defaults["model"] = "changed"

    assert svc.get("agents.defaults.model") == "openai/gpt-4o"


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


def test_save_ui_update_config(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    cfg = tmp_path / "config.jsonc"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save(
        {
            "ui": {
                "language": "zh",
                "update": {
                    "enabled": True,
                    "autoCheck": True,
                    "channel": "stable",
                    "feedUrl": "https://suge8.github.io/Bao/desktop-update.json",
                },
            }
        }
    )
    assert ok is True

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["ui"]["update"]["channel"] == "stable"
    assert data["ui"]["update"]["enabled"] is True
    assert data["ui"]["update"]["feedUrl"] == "https://suge8.github.io/Bao/desktop-update.json"


def test_save_after_missing_load_marks_valid(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()

    def _bootstrap() -> bool:
        cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
        return True

    with (
        patch("bao.config.loader.get_config_path", return_value=cfg),
        patch("bao.config.loader.ensure_first_run", side_effect=_bootstrap),
    ):
        svc.load()
    assert svc.isValid is True

    ok = svc.save({"ui": {"update": {"autoCheck": True}}})
    assert ok is True
    assert svc.isValid is True


def test_load_missing_file_propagates_bootstrap_failure(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()

    with (
        patch("bao.config.loader.get_config_path", return_value=cfg),
        patch("bao.config.loader.ensure_first_run", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
    ):
        svc.load()


def test_load_legacy_ui_language_is_accepted_but_not_promoted(tmp_path):
    from app.backend.config import ConfigService

    config_with_legacy_ui_language = """{
  \"ui\": {
    \"language\": \"zh\"
  },
  \"providers\": {
    \"openaiCompatible\": {
      \"apiKey\": \"sk-test\"
    }
  },
  \"agents\": {
    \"defaults\": {
      \"model\": \"openai/gpt-4o\"
    }
  }
}"""
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_with_legacy_ui_language, encoding="utf-8")

    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    assert svc.isValid is True
    assert svc.get("ui.language") == "zh"
    assert svc.get("ui.update.channel") == "stable"


def test_save_config_default_template_omits_ui_language(tmp_path):
    from app.backend.jsonc_patch import _strip_comments
    from bao.config.loader import save_config
    from bao.config.schema import Config

    cfg = tmp_path / "config.jsonc"
    save_config(Config(), cfg)

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert "language" not in data["ui"]
    assert data["ui"]["update"]["channel"] == "stable"


def test_save_reports_patch_exception(tmp_path):
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    errors = []
    svc.saveError.connect(errors.append)
    with patch("app.backend.config.patch_jsonc", side_effect=ValueError("boom")):
        ok = svc.save({"ui": {"update": {"autoCheck": True}}})

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


def test_get_providers_preserves_config_order_and_hides_internal_fields(tmp_path):
    from app.backend.config import ConfigService

    config_with_ordered_providers = """{
  "providers": {
    "late": {
      "type": "openai",
      "apiKey": "sk-late",
      "order": 5
    },
    "early": {
      "type": "openai",
      "apiKey": "sk-early",
      "extraHeaders": {
        "x-test": "1"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_with_ordered_providers, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    providers = svc.getProviders()
    assert [p["name"] for p in providers] == ["late", "early"]
    assert providers[0] == {
        "name": "late",
        "type": "openai",
        "apiKey": "sk-late",
        "apiBase": "",
    }
    assert "order" not in providers[1]
    assert "extraHeaders" not in providers[1]


def test_save_full_providers_object_with_dotted_name_and_comments(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    config_text = (
        "{\n"
        "  // provider config\n"
        '  "providers": {\n'
        '    "openaiCompatible": {\n'
        '      "type": "openai",\n'
        '      "apiKey": "sk-old",\n'
        '      "apiBase": "https://api.openai.com/v1"\n'
        "    }\n"
        "  },\n"
        '  "agents": {\n'
        '    "defaults": {\n'
        '      "model": "openai/gpt-4o"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_text, encoding="utf-8", newline="\r\n")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save(
        {
            "providers": {
                "foo.bar": {
                    "type": "openai",
                    "apiKey": "sk-new",
                    "apiBase": "https://api.example.com/v1",
                }
            }
        }
    )

    assert ok is True
    written = cfg.read_text(encoding="utf-8")
    assert "// provider config" in written
    assert '// "provider-name": {' in written
    assert '//   "extraHeaders": {},' in written
    data = json.loads(_strip_comments(written))
    assert data["providers"]["foo.bar"]["apiKey"] == "sk-new"
    assert "order" not in data["providers"]["foo.bar"]


def test_save_providers_preserves_explicit_ui_order_for_numeric_names(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments

    config_text = """{
  "providers": {
    "alpha": {
      "type": "openai",
      "apiKey": "sk-alpha"
    },
    "beta": {
      "type": "openai",
      "apiKey": "sk-beta"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_text, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save(
        {
            "providers": [
                {"name": "2", "value": {"type": "openai", "apiKey": "sk-two"}},
                {"name": "10", "value": {"type": "openai", "apiKey": "sk-ten"}},
                {"name": "1", "value": {"type": "openai", "apiKey": "sk-one"}},
            ]
        }
    )

    assert ok is True
    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert list(data["providers"].keys()) == ["2", "10", "1"]


def test_save_provider_named_provider_name_still_injects_template_comment(tmp_path):
    from app.backend.config import ConfigService

    config_text = """{
  "providers": {},
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    cfg = tmp_path / "config.jsonc"
    cfg.write_text(config_text, encoding="utf-8")
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save(
        {
            "providers": {
                "provider-name": {
                    "type": "openai",
                    "apiKey": "sk-real",
                }
            }
        }
    )

    assert ok is True
    written = cfg.read_text(encoding="utf-8")
    assert '// "provider-name": {' in written
    assert '"provider-name": {' in written
    assert written.count('// "provider-name": {') == 1


def test_save_multiple_missing_channel_siblings_in_default_template(tmp_path):
    from app.backend.config import ConfigService
    from app.backend.jsonc_patch import _strip_comments
    from bao.config.loader import save_config
    from bao.config.schema import Config

    cfg = tmp_path / "config.jsonc"
    save_config(Config(), cfg)

    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    ok = svc.save(
        {
            "channels.telegram.enabled": False,
            "channels.discord.enabled": False,
            "channels.slack.enabled": False,
        }
    )

    assert ok is True
    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["channels"]["telegram"]["enabled"] is False
    assert data["channels"]["discord"]["enabled"] is False
    assert data["channels"]["slack"]["enabled"] is False
