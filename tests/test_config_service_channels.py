from __future__ import annotations

import json
from pathlib import Path

from tests._config_service_testkit import MINIMAL_CONFIG, load_service


def test_save_channel_enabled_without_token_fails(tmp_path: Path) -> None:
    svc, _ = load_service(tmp_path)
    errors: list[str] = []
    svc.saveError.connect(errors.append)

    ok = svc.save({"channels.telegram.enabled": True})
    assert ok is False
    assert any("telegram" in error.lower() for error in errors)


def test_save_channel_enabled_with_token_succeeds(tmp_path: Path) -> None:
    config_text = (
        MINIMAL_CONFIG.rstrip("}")
        + ',\n  "channels": {\n    "telegram": {\n      "enabled": false,\n      "token": ""\n    }\n  }\n}'
    )
    svc, _ = load_service(tmp_path, config_text)

    ok = svc.save(
        {
            "channels.telegram.enabled": True,
            "channels.telegram.token": "bot123:TOKEN",
        }
    )
    assert ok is True


def test_save_rejects_invalid_bool_value(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    config_text = (
        MINIMAL_CONFIG.rstrip("}")
        + ',\n  "channels": {\n    "mochat": {\n      "enabled": false,\n      "socketDisableMsgpack": false\n    }\n  }\n}'
    )
    svc, cfg = load_service(tmp_path, config_text)
    errors: list[str] = []
    svc.saveError.connect(errors.append)

    ok = svc.save({"channels.mochat.socketDisableMsgpack": "11"})
    assert ok is False

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert data["channels"]["mochat"]["socketDisableMsgpack"] is False
    assert any("Config validation failed" in error for error in errors)


def test_save_multiple_missing_channel_siblings_in_default_template(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments
    from bao.config.loader import save_config
    from bao.config.schema import Config

    cfg = tmp_path / "config.jsonc"
    save_config(Config(), cfg)
    svc, cfg = load_service(tmp_path, cfg.read_text(encoding="utf-8"))

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
