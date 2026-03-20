from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tests._config_service_testkit import MINIMAL_CONFIG, load_service


def test_save_patches_value(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    svc, cfg = load_service(tmp_path)
    ok = svc.save({"agents.defaults.model": "anthropic/claude-3-5-sonnet"})
    assert ok is True

    written = cfg.read_text(encoding="utf-8")
    assert "// provider config" in written
    data = json.loads(_strip_comments(written))
    assert data["agents"]["defaults"]["model"] == "anthropic/claude-3-5-sonnet"


def test_save_reasoning_effort_off(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    svc, cfg = load_service(tmp_path)
    assert svc.save({"agents.defaults.reasoningEffort": "off"}) is True

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["agents"]["defaults"]["reasoningEffort"] == "off"


def test_save_service_tier_priority(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    svc, cfg = load_service(tmp_path)
    assert svc.save({"agents.defaults.serviceTier": "priority"}) is True

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["agents"]["defaults"]["serviceTier"] == "priority"


def test_save_ui_update_config(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    svc, cfg = load_service(tmp_path)
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


def test_save_after_missing_load_marks_valid(tmp_path: Path) -> None:
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
    assert svc.save({"ui": {"update": {"autoCheck": True}}}) is True
    assert svc.isValid is True


def test_save_config_default_template_omits_ui_language(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments
    from bao.config._loader_template import JSONC_TEMPLATE
    from bao.config.loader import save_config
    from bao.config.schema import Config

    cfg = tmp_path / "config.jsonc"
    save_config(Config(), cfg)

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert "language" not in data["ui"]
    assert data["ui"]["update"]["channel"] == "stable"
    assert '"sandboxMode": "semi-auto"' in JSONC_TEMPLATE
    assert "仅拦明显危险命令（默认）" in JSONC_TEMPLATE
    assert "不会" not in JSONC_TEMPLATE


def test_save_reports_patch_exception(tmp_path: Path) -> None:
    from app.backend.config import ConfigService

    cfg = tmp_path / "config.jsonc"
    svc = ConfigService()
    with patch("bao.config.loader.get_config_path", return_value=cfg):
        svc.load()

    errors: list[str] = []
    svc.saveError.connect(errors.append)
    with patch("app.backend.config.patch_jsonc", side_effect=ValueError("boom")):
        ok = svc.save({"ui": {"update": {"autoCheck": True}}})

    assert ok is False
    assert any("Patch failed" in error for error in errors)


def test_save_before_load_fails() -> None:
    from app.backend.config import ConfigService

    svc = ConfigService()
    assert svc.save({"agents.defaults.model": "x"}) is False
