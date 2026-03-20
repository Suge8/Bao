from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tests._config_service_testkit import MINIMAL_CONFIG, load_service


def test_load_missing_file(tmp_path: Path) -> None:
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


def test_load_valid_config(tmp_path: Path) -> None:
    svc, _ = load_service(tmp_path)
    assert svc.isValid is True


def test_get_value_after_load(tmp_path: Path) -> None:
    svc, _ = load_service(tmp_path)
    assert svc.get("agents.defaults.model") == "openai/gpt-4o"
    assert svc.get("providers.openaiCompatible.apiKey") == "sk-test"
    assert svc.get("nonexistent.path", "fallback") == "fallback"


def test_get_value_slot(tmp_path: Path) -> None:
    svc, _ = load_service(tmp_path)
    assert svc.getValue("agents.defaults.temperature") == 0.7


def test_get_config_file_path_after_load(tmp_path: Path) -> None:
    svc, cfg = load_service(tmp_path)
    assert svc.getConfigFilePath() == str(cfg)


def test_open_config_directory_uses_parent_folder(tmp_path: Path) -> None:
    from app.backend.config import QDesktopServices

    svc, cfg = load_service(tmp_path)
    with patch.object(QDesktopServices, "openUrl") as open_url:
        svc.openConfigDirectory()

    open_url.assert_called_once()
    url = open_url.call_args.args[0]
    assert url.isLocalFile()
    assert Path(url.toLocalFile()) == cfg.parent


def test_export_data_returns_detached_snapshot(tmp_path: Path) -> None:
    svc, _ = load_service(tmp_path)

    snapshot = svc.exportData()
    agents = snapshot["agents"]
    assert isinstance(agents, dict)
    defaults = agents["defaults"]
    assert isinstance(defaults, dict)
    defaults["model"] = "changed"
    assert svc.get("agents.defaults.model") == "openai/gpt-4o"


def test_load_missing_file_propagates_bootstrap_failure(tmp_path: Path) -> None:
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()
    with (
        patch("bao.config.loader.get_config_path", return_value=cfg),
        patch("bao.config.loader.ensure_first_run", side_effect=RuntimeError("boom")),
    ):
        try:
            svc.load()
        except RuntimeError as exc:
            assert "boom" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_load_legacy_ui_language_is_accepted_but_not_promoted(tmp_path: Path) -> None:
    config_text = """{
  "ui": {
    "language": "zh"
  },
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-test"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    svc, _ = load_service(tmp_path, config_text)

    assert svc.isValid is True
    assert svc.get("ui.language") == "zh"
    assert svc.get("ui.update.channel") == "stable"
